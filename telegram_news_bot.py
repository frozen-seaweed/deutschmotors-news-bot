import requests
import os
from datetime import datetime, timedelta

# GitHub Secrets에서 환경변수 가져오기
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID') 
NEWS_API_KEY = os.environ.get('NEWS_API_KEY')

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
    """자동차 중심 뉴스 수집"""
    articles = []
    
    try:
        # 1. 한국 자동차 뉴스 (2개)
        print("🚗 한국 자동차 뉴스 수집 중...")
        korean_auto_params = {
            'q': '현대차 OR 기아 OR 자동차 OR 전기차 OR EV OR 배터리 OR 충전소',
            'language': 'ko',
            'sortBy': 'publishedAt',
            'pageSize': 5,
            'apiKey': NEWS_API_KEY
        }
        
        response = requests.get("https://newsapi.org/v2/everything", params=korean_auto_params)
        data = response.json()
        
        if data.get('status') == 'ok':
            count = 0
            for article in data['articles']:
                if article['title'] and article['url'] and count < 2:
                    articles.append({
                        'category': '🇰🇷 국내 모빌리티',
                        'title': article['title'],
                        'description': clean_text(article.get('description', '요약 없음')),
                        'url': article['url']
                    })
                    count += 1
        
        # 2. 해외 자동차 뉴스 (2개) - 영어 뉴스를 한국어로 번역
        print("🌍 해외 모빌리티 뉴스 수집 중...")
        
        # 최근 2일 뉴스만 가져오기
        two_days_ago = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
        
        global_auto_params = {
            'q': 'Tesla OR BMW OR Mercedes OR Volkswagen OR Toyota OR Ford OR electric vehicle OR EV OR autonomous',
            'language': 'en',
            'sortBy': 'publishedAt',
            'from': two_days_ago,
            'pageSize': 5,
            'apiKey': NEWS_API_KEY
        }
        
        response = requests.get("https://newsapi.org/v2/everything", params=global_auto_params)
        data = response.json()
        
        if data.get('status') == 'ok':
            count = 0
            for article in data['articles']:
                if article['title'] and article['url'] and count < 2:
                    # 제목과 설명을 한국어로 번역
                    translated_title = translate_to_korean(article['title'])
                    translated_desc = translate_to_korean(article.get('description', 'No description'))
                    
                    articles.append({
                        'category': '🌍 해외 모빌리티',
                        'title': translated_title,
                        'description': clean_text(translated_desc),
                        'url': article['url']  # 원문 링크 유지
                    })
                    count += 1
                    
    except Exception as e:
        print(f"뉴스 수집 오류: {e}")
        # 오류시 테스트 뉴스 반환
        articles = [{
            'category': '🔧 알림',
            'title': '뉴스 시스템 점검 중입니다',
            'description': '잠시 후 다시 시도해주세요.',
            'url': 'https://www.naver.com'
        }]
    
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
    message += " " * + "\n\n"
    
    for i, article in enumerate(articles, 1):
        # 카테고리 표시
        category_clean = article['category']
        
        message += f"*{i}. [{category_clean}]*\n"
        message += f"*{article['title']}*\n"
        message += f"{article['description']}\n"
        message += f"[📖 Read More]({article['url']})\n\n"
    
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

def main():
    """메인 실행 함수"""
    print("🚗 도이치모터스 자동차 뉴스봇 시작!")
    
    # 환경변수 확인
    if not all([BOT_TOKEN, CHAT_ID, NEWS_API_KEY]):
        print("❌ 환경변수가 설정되지 않았습니다.")
        print(f"BOT_TOKEN: {'설정됨' if BOT_TOKEN else '없음'}")
        print(f"CHAT_ID: {'설정됨' if CHAT_ID else '없음'}")
        print(f"NEWS_API_KEY: {'설정됨' if NEWS_API_KEY else '없음'}")
        return
    
    # 자동차 뉴스 수집
    articles = get_automotive_news()
    print(f"🚗 총 {len(articles)}개 자동차 뉴스 수집 완료")
    
    # 메시지 생성 및 전송
    message = create_telegram_message(articles)
    success = send_to_telegram(message)
    
    if success:
        print("🎉 모든 작업 완료!")
    else:
        print("😅 일부 오류가 발생했습니다.")

# 스크립트 실행
if __name__ == "__main__":
    main()
