import requests
import os
import json
import hashlib
from datetime import datetime, timedelta

# GitHub Secrets에서 환경변수 가져오기
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID') 
NEWS_API_KEY = os.environ.get('NEWS_API_KEY')

# 전송된 기사 기록을 저장할 파일명
SENT_ARTICLES_FILE = 'sent_articles.json'

def load_sent_articles():
    """이전에 전송된 기사 목록 로드"""
    try:
        if os.path.exists(SENT_ARTICLES_FILE):
            with open(SENT_ARTICLES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 7일 이상 된 기록은 삭제 (메모리 절약)
                cutoff_date = datetime.now() - timedelta(days=7)
                filtered_data = {
                    url: timestamp for url, timestamp in data.items()
                    if datetime.fromisoformat(timestamp) > cutoff_date
                }
                return filtered_data
        return {}
    except Exception as e:
        print(f"전송 기록 로드 오류: {e}")
        return {}

def save_sent_articles(sent_articles):
    """전송된 기사 목록 저장"""
    try:
        with open(SENT_ARTICLES_FILE, 'w', encoding='utf-8') as f:
            json.dump(sent_articles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"전송 기록 저장 오류: {e}")

def create_article_hash(title, url):
    """기사의 고유 해시값 생성 (제목 + URL 기반)"""
    content = f"{title.strip().lower()}{url}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def is_duplicate_article(article, sent_articles):
    """중복 기사인지 확인"""
    article_hash = create_article_hash(article['title'], article['url'])
    
    # URL 기반 중복 확인
    if article['url'] in sent_articles:
        return True
    
    # 제목 유사도 기반 중복 확인 (간단한 키워드 매칭)
    title_words = set(article['title'].lower().split())
    for sent_url, timestamp in sent_articles.items():
        # 제목이 80% 이상 유사하면 중복으로 간주
        if len(title_words) > 0:
            similarity = len(title_words.intersection(set(sent_url.split('/')[-1].lower().split('-')))) / len(title_words)
            if similarity > 0.8:
                return True
    
    return False

def translate_to_korean(text):
    """간단한 번역 함수 (Google Translate API 무료 버전)"""
    try:
        # Google Translate의 무료 엔드포인트 사용
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            'client': 'gtx',
            'sl': 'en',  # 영어에서
            'tl': 'ko',  # 한국어로
            'dt': 't',
            'q': text
        }
        
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            result = response.json()
            translated = result[0][0][0]
            return translated
        else:
            return text  # 번역 실패시 원문 반환
            
    except Exception as e:
        print(f"번역 오류: {e}")
        return text  # 오류시 원문 반환

def get_automotive_news():
    """자동차 중심 뉴스 수집 (국내 뉴스만)"""
    articles = []
    sent_articles = load_sent_articles()
    
    try:
        # ✅ 한국 자동차 뉴스만 수집
        print("🚗 한국 자동차 뉴스 수집 중...")
        korean_auto_params = {
            'q': '모빌리티 OR 딜러사 OR 현대차 OR 기아 OR 자동차 OR 전기차 OR EV OR 배터리 OR 충전소',
            'language': 'ko',
            'sortBy': 'publishedAt',
            'pageSize': 10,
            'apiKey': NEWS_API_KEY
        }
        
        response = requests.get("https://newsapi.org/v2/everything", params=korean_auto_params)
        data = response.json()
        
        if data.get('status') == 'ok':
            count = 0
            for article in data['articles']:
                if article['title'] and article['url'] and count < 2:
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
                        print(f"⏭️  중복 국내 뉴스 건너뛰기: {article['title'][:50]}...")
    
    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        test_article = {
            'category': '🔧 알림',
            'title': f'뉴스 시스템 점검 중입니다 - {datetime.now().strftime("%H:%M")}',
            'description': '잠시 후 다시 시도해주세요.',
            'url': f'https://www.naver.com?t={int(datetime.now().timestamp())}'
        }
        
        if not is_duplicate_article(test_article, sent_articles):
            articles = [test_article]
    
    return articles

def clean_text(text):
    """텍스트 정리 함수"""
    if not text or text == 'None' or text == 'No description':
        return "요약 정보 없음"
    
    # 불필요한 문자 제거
    clean = text.replace('\n', ' ').replace('\r', '').replace('\t', ' ')
    clean = clean.replace('[', '').replace(']', '')
    clean = clean.replace('(', '').replace(')', '')
    
    # 연속된 공백 제거
    import re
    clean = re.sub(r'\s+', ' ', clean).strip()
    
    # 길이 제한
    if len(clean) > 120:
        return clean[:120] + "..."
    
    return clean

def create_telegram_message(articles):
    """깔끔한 텔레그램 메시지 생성"""
    today = datetime.now().strftime('%Y년 %m월 %d일 %A')
    
    # 요일을 한글로 변환
    weekdays = {
        'Monday': '월요일', 'Tuesday': '화요일', 'Wednesday': '수요일',
        'Thursday': '목요일', 'Friday': '금요일', 'Saturday': '토요일', 'Sunday': '일요일'
    }
    for eng, kor in weekdays.items():
        today = today.replace(eng, kor)
    
    message = f"*DeutschMotors News Bot*\n"
    message += f"{today}\n"
    message += "\n"
    
    if not articles:
        message += "🔍 오늘은 새로운 자동차 뉴스가 없습니다.\n"
        message += "내일 다시 확인해주세요! 🚗"
        return message
    
    for i, article in enumerate(articles, 1):
        # 카테고리 표시
        category_clean = article['category']
        
        message += f"*{i}. {article['title']}*\n"
        message += f"{article['description']}\n"
        message += f"[📖 Read More]({article['url']})\n\n"
        
        message += "\n"
    
    return message

def send_to_telegram(message):
    """텔레그램으로 메시지 보내기"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    data = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': False
    }
    
    try:
        response = requests.post(url, json=data)
        result = response.json()
        
        if result.get('ok'):
            print("✅ 텔레그램 전송 성공!")
            return True
        else:
            print(f"❌ 전송 실패: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 전송 오류: {e}")
        return False

def update_sent_articles(articles):
    """전송된 기사 목록 업데이트"""
    sent_articles = load_sent_articles()
    current_time = datetime.now().isoformat()
    
    for article in articles:
        sent_articles[article['url']] = current_time
    
    save_sent_articles(sent_articles)
    print(f"📝 {len(articles)}개 기사를 전송 기록에 추가했습니다.")

def main():
    """메인 실행 함수"""
    print("🚗 도이치모터스 자동차 뉴스봇 시작!")
    print("🔍 중복 기사 확인 시스템 활성화")
    
    # 환경변수 확인
    if not all([BOT_TOKEN, CHAT_ID, NEWS_API_KEY]):
        print("❌ 환경변수가 설정되지 않았습니다.")
        print(f"BOT_TOKEN: {'설정됨' if BOT_TOKEN else '없음'}")
        print(f"CHAT_ID: {'설정됨' if CHAT_ID else '없음'}")
        print(f"NEWS_API_KEY: {'설정됨' if NEWS_API_KEY else '없음'}")
        return
    
    # 자동차 뉴스 수집 (중복 제거 포함)
    articles = get_automotive_news()
    print(f"🚗 중복 제거 후 {len(articles)}개 새로운 자동차 뉴스 선별 완료")
    
    # 새로운 기사가 있는 경우만 전송
    if articles:
        # 메시지 생성 및 전송
        message = create_telegram_message(articles)
        success = send_to_telegram(message)
        
        if success:
            # 전송 성공시 기사 목록 업데이트
            update_sent_articles(articles)
            print("🎉 모든 작업 완료!")
        else:
            print("😅 전송 실패로 기사 기록을 업데이트하지 않았습니다.")
    else:
        print("📰 새로운 기사가 없어서 메시지를 전송하지 않았습니다.")
        # 빈 메시지라도 전송하려면 아래 주석 해제
        # message = create_telegram_message(articles)
        # send_to_telegram(message)

# 스크립트 실행
if __name__ == "__main__":
    main()
