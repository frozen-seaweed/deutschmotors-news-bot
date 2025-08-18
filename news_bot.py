import requests
import os
from storage import build_keyword_weights, score_article

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

def get_news():
    url = "https://newsapi.org/v2/everything"
    params = {
        'q': '자동차 OR 현대차 OR EV OR 배터리 OR 모빌리티 OR 기아',
        'language': 'ko',
        'pageSize': 10,
        'sortBy': 'publishedAt',
        'apiKey': NEWS_API_KEY
    }
    response = requests.get(url, params=params)
    return response.json().get("articles", [])

def send_news(article):
    keyboard = {
        "inline_keyboard": [
            [{"text": "👍 좋아요", "callback_data": f"like:{article['url']}"}]
        ]
    }
    text = f"{article['title']}\n\n{article.get('description', '')}\n{article['url']}"
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "reply_markup": keyboard
    }
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=data)

def send_daily_news():
    articles = get_news()
    keyword_weights = build_keyword_weights()
    sorted_articles = sorted(articles, key=lambda a: score_article(a, keyword_weights), reverse=True)

    for article in sorted_articles[:4]:
        send_news(article)
