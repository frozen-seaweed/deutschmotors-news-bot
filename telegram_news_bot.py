# telegram_news_bot.py
import os, re, requests
from datetime import datetime
from storage import (
    build_keyword_weights,
    load_sent_articles,
    save_sent_articles,
    normalize_url,
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

def get_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "자동차 OR 현대차 OR EV OR 배터리 OR 모빌리티 OR 기아",
        "language": "ko",
        "pageSize": 20,      # 넉넉히 가져와서 필터링
        "sortBy": "publishedAt",
        "apiKey": NEWS_API_KEY,
    }
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json().get("articles", [])

def score_article(article, keyword_weights):
    text = f"{article.get('title','')} {article.get('description','')}".lower()
    score = 0
    for kw, w in (keyword_weights or {}).items():
        if kw.lower() in text:
            score += int(w) if isinstance(w, int) else 1
    return score

def normalize_title(t: str) -> str:
    t = t or ""
    t = re.sub(r"[\[\](){}“”\"'‘’]", "", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t

def send_news(article):
    # ✅ 필수 ENV 확인 (없으면 바로 실패 이유가 로그에 찍혀요)
    if not BOT_TOKEN:
        raise RuntimeError("ENV TELEGRAM_BOT_TOKEN 이 비어있습니다.")
    if not CHAT_ID:
        raise RuntimeError("ENV TELEGRAM_CHAT_ID 이 비어있습니다. (채널이면 -100... 숫자ID 권장)")

    # 1) 데이터 추출
    title = (article.get("title") or "").strip()
    desc  = (article.get("description") or "").strip()
    link  = (article.get("url") or "").strip()

    # 2) 파싱 문제 없는 '순수 텍스트' 본문 (parse_mode 사용 안 함)
    text = f"📰 {title}\n\n{desc}\n\n{link}"

    # 3) 인라인 키보드는 그대로 유지 (콜백 저장은 나중 단계에서)
    payload = {
        "chat_id": CHAT_ID,   # 채널이면 -100... 숫자ID 쓰는 게 가장 안전
        "text": text,
        "reply_markup": {"inline_keyboard": [[{"text": "👍 좋아요", "callback_data": "like"}]]}
        # ⛔ parse_mode 제거: Markdown/HTML 파싱 에러 원천 차단
    }

    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json=payload, timeout=20
    )

    # 4) 텔레그램 응답 그대로 확인 (왜 거절됐는지 바로 보이게)
    ct = r.headers.get("Content-Type", "")
    if "application/json" in ct:
        data = r.json()
        print("Telegram API response:", data)  # GitHub Actions 로그에서 확인
        if not data.get("ok"):
            # 예: "Bad Request: chat not found", "Forbidden: bot is not a member..."
            raise RuntimeError(f"Telegram error: {data}")
    else:
        # 토큰 오타 등으로 JSON이 아닐 때
        print("Telegram HTTP:", r.status_code, r.text)
        r.raise_for_status()





def send_daily_news():
    # 1) 수집
    articles = get_news()

    # 2) 과거 전송 기록(깃허브) 로드
    sent_map, sent_sha = load_sent_articles()

    # 3) 정규화 기반 중복 제거 (URL + 제목)
    uniq, seen_urls, seen_titles = [], set(), set()
    for a in articles:
        url = a.get("url")
        title = a.get("title")
        if not url or not title:
            continue

        nurl = normalize_url(url)
        ntit = normalize_title(title)

        if nurl in sent_map:     # 과거에 보냄 → 스킵
            continue
        if nurl in seen_urls:    # 같은 실행 내 중복 URL → 스킵
            continue
        if ntit in seen_titles:  # 같은 실행 내 제목 중복 → 스킵
            continue

        seen_urls.add(nurl)
        seen_titles.add(ntit)
        uniq.append(a)

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
