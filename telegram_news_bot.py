import requests
import os
import json
import hashlib
from datetime import datetime, timedelta

# 환경변수
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
NEWS_API_KEY = os.environ.get('NEWS_API_KEY')

SENT_ARTICLES_FILE = 'sent_articles.json'

def load_sent_articles():
    try:
        if os.path.exists(SENT_ARTICLES_FILE):
            with open(SENT_ARTICLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                cutoff_date = datetime.now() - timedelta(days=7)
                return {
                    url: ts for url, ts in data.items()
                    if datetime.fromisoformat(ts) > cutoff_date
                }
        return {}
    except Exception as e:
        print(f"전송 기록 로드 오류: {e}")
        return {}

def save_sent_articles(sent_articles):
    try:
        with open(SENT_ARTICLES_FILE, 'w', encoding='utf-8') as f:
            json.dump(sent_articles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"전송 기록 저장 오류: {e}")

def create_article_hash(title, url):
    content = f"{title.strip().lower()}{url}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def is_duplicate_article(article, sent_articles):
    article_hash = create_article_hash(article['title'], article['url'])
    if article['url'] in sent_articles:
        return True

    title_words = set(article['title'].lower().split())
    for sent_url in sent_articles:
        similarity = len(title_words.intersection(set(sent_url.split('/')[-1].lower().split('-')))) / len(title_words)
        if similarity > 0.8:
            return True
    return False

def clean_text(text):
    if not text or text in ['None', 'No description']:
        return "요약 정보 없음"
    import re
    text = re.sub(r'[\n\r\t]+', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 120:
        return text[:120] + "..."
    return text

def get_automotive_news():
    articles = []
    sent_articles = load_sent_articles()

    try:
        print("🚗 한국 자동차 뉴스 수집 중...")
        params = {
            'q': '모빌리티 OR 딜러사 OR 현대차 OR 기아 OR 자동차 OR 전기차 OR EV OR 배터리 OR 충전소',
            'language': 'ko',
            'sortBy': 'publishedAt',
            'pageSize': 10,
            'apiKey': NEWS_API_KEY
        }

        response = requests.get("https://newsapi.org/v2/everything", params=params)
        data = response.json()

        if data.get('status') == 'ok':
            count = 0
            for article in data['articles']:
                if article['title'] and article['url'] and count < 4:
                    article_data = {
                        'category': '국내 News',
                        'title': article['title'],
                        'description': clean_text(article.get('description', '요약 없음')),
                        'url': article['url']
                    }
                    if not is_duplicate_article(article_data, sent_articles):
                        articles.append(article_data)
                        count += 1
                        print(f"✅ 새로운 국내 뉴스: {article['title'][:50]}...")
                    else:
                        print(f"⏭️  중복 뉴스 건너뛰기: {article['title'][:50]}...")

    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        fallback = {
            'category': '🔧 알림',
            'title': f'뉴스 시스템 점검 중입니다 - {datetime.now().strftime("%H:%M")}',
            'description': '잠시 후 다시 시도해주세요.',
            'url': 'https://www.naver.com'
        }
        if not is_duplicate_article(fallback, sent_articles):
            articles = [fallback]

    return articles

def send_article_to_telegram(article):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    text = f"*{article['title']}*\n{article['description']}\n[📖 더보기]({article['url']})"

    keyboard = {
        "inline_keyboard": [
            [{"text": "👍 좋아요", "callback_data": f"like:{article['url']}"}]
        ]
    }

    data = {
        'chat_id': CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown',
        'reply_markup': keyboard
    }

    try:
        response = requests.post(url, json=data)
        result = response.json()
        if result.get('ok'):
            print(f"✅ 전송 성공: {article['title'][:30]}...")
            return True
        else:
            print(f"❌ 전송 실패: {result}")
            return False
    except Exception as e:
        print(f"❌ 전송 오류: {e}")
        return False

def update_sent_articles(articles):
    sent_articles = load_sent_articles()
    now = datetime.now().isoformat()
    for article in articles:
        sent_articles[article['url']] = now
    save_sent_articles(sent_articles)
    print(f"📝 {len(articles)}개 기사를 전송 기록에 추가했습니다.")

def main():
    print("🚗 도이치모터스 자동차 뉴스봇 시작!")
    if not all([BOT_TOKEN, CHAT_ID, NEWS_API_KEY]):
        print("❌ 환경변수가 누락되었습니다.")
        return

    articles = get_automotive_news()
    print(f"📦 총 {len(articles)}개의 새로운 뉴스 준비 완료!")

    success_count = 0
    for article in articles:
        if send_article_to_telegram(article):
            success_count += 1

    if success_count > 0:
        update_sent_articles(articles)
        print("🎉 전송 완료!")
    else:
        print("😅 뉴스 전송에 실패했거나 보낼 뉴스가 없습니다.")

if __name__ == "__main__":
    main()
