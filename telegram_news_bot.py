# telegram_news_bot.py
# ✅ 그대로 파일 전체를 이 코드로 교체하세요.

import os
import re
import requests
from datetime import datetime, timedelta
from storage import (
    build_keyword_weights,
    load_sent_articles,
    save_sent_articles,
    normalize_url,
)

# ─────────────────────────────────────────────────────────────────────────────
# 환경 변수
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# ─────────────────────────────────────────────────────────────────────────────
# 동적 쿼리 생성 + 뉴스 수집
def get_news():
    """
    좋아요 상위 키워드로 동적 q를 만들어 NewsAPI에서 기사 수집.
    - liked_keywords 상위 6개를 OR로 묶어 q 생성
    - 데이터가 적으면 기본 q로 폴백
    - 최근 기사 위주로 36시간 범위(from=) 적용
    - 로그 한 줄 남김: q / fetched / total / since
    """
    # 1) 기본 q (폴백용)
    base_q = "자동차 OR 현대차 OR EV OR 배터리 OR 모빌리티 OR 기아"

    # 2) 선호 키워드 상위 N 추출
    try:
        weights = build_keyword_weights() or {}
    except Exception:
        weights = {}

    topK = []
    if isinstance(weights, dict):
        # 점수 내림차순 상위 6개
        topK = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:6]

    liked_terms = []

    # 간단 동의어/정규화 (필요 최소만)
    syn = {
        "ev": "전기차",
        "벤츠": "메르세데스",
    }

    for kw, _score in topK:
        if not kw:
            continue
        k = str(kw).strip()
        if not k:
            continue
        # 동의어 매핑
        lk = syn.get(k.lower(), k)
        # 멀티워드는 따옴표로 감싸기
        if " " in lk:
            liked_terms.append(f"\"{lk}\"")
        else:
            liked_terms.append(lk)

    # 3) 최종 q 구성 (선호 있으면 선호 OR 기본, 없으면 기본 q)
    if liked_terms:
        q = f"({' OR '.join(liked_terms)}) OR ({base_q})"
    else:
        q = base_q

    # 4) 최근성 필터: 지난 36시간(UTC)
    since = (datetime.utcnow() - timedelta(hours=36)).isoformat(timespec="seconds") + "Z"

    # 5) NewsAPI 호출
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": q,
        "language": "ko",
        "pageSize": 20,            # 필요 시 30으로 늘릴 수 있음
        "sortBy": "publishedAt",
        "from": since,
        # "searchIn": "title,description",  # 필요하면 주석 해제
        "apiKey": NEWS_API_KEY,
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    articles = data.get("articles", []) or []

    # 6) 로그 한 줄 (Actions 로그에서 원인 파악 쉬움)
    try:
        total = data.get("totalResults")
        print(f"[get_news] q='{q}' fetched={len(articles)} total={total} since={since}")
    except Exception:
        pass

    return articles

# ─────────────────────────────────────────────────────────────────────────────
# 점수 계산(선호 키워드 기반)
def score_article(article, keyword_weights):
    text = f"{article.get('title','')} {article.get('description','')}".lower()
    score = 0
    for kw, w in (keyword_weights or {}).items():
        k = str(kw).lower()
        if k and k in text:
            try:
                score += int(w)
            except Exception:
                score += 1
    return score

# 제목 정규화(중복 제거용)
def normalize_title(t: str) -> str:
    t = t or ""
    t = re.sub(r"[\[\](){}“”\"'‘’]", "", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t

# ─────────────────────────────────────────────────────────────────────────────
# 텔레그램 전송
def send_news(article):
    # 버튼: callback_data는 'like'만 써도 됨(웹훅은 제목 파싱 기반)
    kb = {"inline_keyboard": [[{"text": "👍 좋아요", "callback_data": "like"}]]}

    title = article.get("title", "") or ""
    desc  = article.get("description", "") or ""
    link  = article.get("url", "") or ""

    # 제목 라인은 '📰 '로 시작 → webhook의 제목 파서가 안정적으로 잡음
    text = f"📰 {title}\n\n{desc}\n\n{link}"

    payload = {"chat_id": CHAT_ID, "text": text, "reply_markup": kb}
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=payload, timeout=20
    )
    if r.status_code != 200:
        print("Telegram error:", r.status_code, r.text)
    r.raise_for_status()

# ─────────────────────────────────────────────────────────────────────────────
# 메인 루틴
def send_daily_news():
    # 1) 수집
    articles = get_news()

    # 2) 과거 전송 기록(깃허브) 로드
    sent_map, sent_sha = load_sent_articles()

    # 3) 정규화 기반 중복 제거 (URL + 제목)
    uniq, seen_urls, seen_titles = [], set(), set()
    url_dup = title_dup = 0

    for a in articles:
        url = a.get("url")
        title = a.get("title")
        if not url or not title:
            continue

        nurl = normalize_url(url)
        ntit = normalize_title(title)

        if nurl in sent_map:     # 과거에 보냄 → 스킵
            url_dup += 1
            continue
        if nurl in seen_urls:    # 같은 실행 내 중복 URL → 스킵
            url_dup += 1
            continue
        if ntit in seen_titles:  # 같은 실행 내 제목 중복 → 스킵
            title_dup += 1
            continue

        seen_urls.add(nurl)
        seen_titles.add(ntit)
        uniq.append(a)

    # 중복 로그
    try:
        print(f"[dedup] kept={len(uniq)} hist={len(sent_map)} urlDup={url_dup} titleDup={title_dup}")
    except Exception:
        pass

    if not uniq:
        print("No new unique articles.")
        return

    # 4) 좋아요 학습 가중치 반영해서 정렬
    kw_weights = build_keyword_weights()
    uniq.sort(key=lambda a: score_article(a, kw_weights), reverse=True)

    # 5) 상위 4건 전송
    picked = uniq[:4]
    for art in picked:
        send_news(art)

    # 6) 전송 기록 저장 (정규화 URL을 키로 저장)
    now = datetime.utcnow().isoformat() + "Z"
    for art in picked:
        nurl = normalize_url(art.get("url",""))
        if nurl:
            sent_map[nurl] = now
    save_sent_articles(sent_map, sent_sha)

if __name__ == "__main__":
    send_daily_news()
