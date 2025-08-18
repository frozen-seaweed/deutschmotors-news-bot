# new_bot.py
import os
import requests
from datetime import datetime
from storage import build_keyword_weights, load_sent_articles, save_sent_articles

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

def get_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "자동차 OR 현대차 OR EV OR 배터리 OR 모빌리티 OR 기아",
        "language": "ko",
        "pageSize": 20,              # 넉넉히 가져와서 필터링
        "sortBy": "publishedAt",
        "apiKey": NEWS_API_KEY,
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("articles", [])

def score_article(article, keyword_weights):
    """간단 점수: 제목+설명에 키워드가 있으면 가중치 더하기"""
    text = f"{article.get('title','')} {article.get('description','')}".lower()
    score = 0
    for kw, w in keyword_weights.items():
        if kw.lower() in text:
            score += int(w) if isinstance(w, int) else 1
    return score

def send_news(article):
    keyboard = {
        "inline_keyboard": [
            [{"text": "👍 좋아요", "callback_data": f"like:{article['url']}"}],
            # 필요하면 싫어요도 추가: [{"text":"👎 싫어요", "callback_data": f"dislike:{article['url']}"}]
        ]
    }
    title = article.get("title", "")
    desc = article.get("description", "") or ""
    link = article.get("url", "")

    text = f"📰 {title}\n\n{desc}\n\n{link}"
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "reply_markup": keyboard,
        # "disable_web_page_preview": False,  # 미리보기 끄려면 True
    }
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=data, timeout=15
    )
    r.raise_for_status()

def send_daily_news():
    # 1) 뉴스 수집
    articles = get_news()

    # 2) 이미 보낸 URL 목록 불러오기(깃허브에서)
    sent_map, sent_sha = load_sent_articles()

    # 3) 중복(이미 전송) 제거 + 현재 목록 내부 중복 제거
    uniq = []
    seen_now = set()
    for a in articles:
        url = a.get("url")
        title = a.get("title")
        if not url or not title:
            continue
        if url in sent_map:   # 과거에 보낸 적 있음 → 스킵
            continue
        if url in seen_now:   # 같은 실행 내 중복 → 스킵
            continue
        seen_now.add(url)
        uniq.append(a)

    if not uniq:
        print("No new articles today.")
        return

    # 4) 키워드 가중치(좋아요 학습) 불러와서 점수 계산
    kw_weights = build_keyword_weights()
    sorted_articles = sorted(
        uniq,
        key=lambda a: score_article(a, kw_weights),
        reverse=True
    )

    # 5) 상위 4개만 전송
    picked = sorted_articles[:4]
    for art in picked:
        send_news(art)

    # 6) 전송한 URL 깃허브에 기록
    now = datetime.utcnow().isoformat() + "Z"
    for art in picked:
        sent_map[art["url"]] = now
    save_sent_articles(sent_map, sent_sha)

if __name__ == "__main__":
    send_daily_news()
