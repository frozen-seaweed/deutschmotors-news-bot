import requests
import os
from datetime import datetime

# GitHub Secrets에서 환경변수 가져오기
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID') 
NEWS_API_KEY = os.environ.get('NEWS_API_KEY')

def get_korean_news():
    """한국 뉴스를 가져오는 함수"""
    articles = []
    
    try:
        # 경제 뉴스
        print("📈 경제 뉴스 수집 중...")
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            'country': 'kr',
            'category': 'business',
            'pageSize': 2,
            'apiKey': NEWS_API_KEY
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get('status') == 'ok':
            for article in data['articles'][:2]:
                if article['title'] and article['url']:
                    articles.append({
                        'category': '📈 경제',
                        'title': article['title'],
                        'description': clean_text(article.get('description', '요약 없음')),
                        'url': article['url']
                    })
        
        # 자동차 뉴스
        print("🚗 자동차 뉴스 수집 중...")
        url2 = "https://newsapi.org/v2/everything"
        params2 = {
            'q': '현대차 OR 기아 OR 자동차 OR 전기차',
            'language': 'ko',
            'sortBy': 'publishedAt',
            'pageSize': 2,
            'apiKey': NEWS_API_KEY
        }
        
        response2 = requests.get(url2, params=params2)
        data2 = response2.json()
        
        if data2.get('status') == 'ok':
            for article in data2['articles'][:2]:
                if article['title'] and article['url']:
                    articles.append({
                        'category': '🚗 자동차',
                        'title': article['title'],
                        'description': clean_text(article.get('description', '요약 없음')),
                        'url': article['url']
                    })
                    
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
    if not text or text == 'None':
        return "요약 정보 없음"
    
    # 불필요한 문자 제거
    clean = text.replace('\n', ' ').replace('\r', '')
    clean = clean.replace('[', '').replace(']', '')
    
    # 길이 제한
    if len(clean) > 100:
        return clean[:100] + "..."
    
    return clean

def create_telegram_message(articles):
    """텔레그램 메시지 만들기"""
    today = datetime.now().strftime('%Y년 %m월 %d일 %A')
    
    message = f"🌅 *도이치모터스 모닝 뉴스*\n"
    message += f"📅 {today}\n\n"
    
    for i, article in enumerate(articles, 1):
        message += f"{article['category']} *{article['title']}*\n"
        message += f"💬 {article['description']}\n"
        message += f"🔗 [기사 보기]({article['url']})\n\n"
    
    message += "━━━━━━━━━━━━━━━━━━━\n"
    message += "📱 자동 발송 | 도이치모터스"
    
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
    print("🤖 도이치모터스 뉴스봇 시작!")
    
    # 환경변수 확인
    if not all([BOT_TOKEN, CHAT_ID, NEWS_API_KEY]):
        print("❌ 환경변수가 설정되지 않았습니다.")
        print(f"BOT_TOKEN: {'설정됨' if BOT_TOKEN else '없음'}")
        print(f"CHAT_ID: {'설정됨' if CHAT_ID else '없음'}")
        print(f"NEWS_API_KEY: {'설정됨' if NEWS_API_KEY else '없음'}")
        return
    
    # 뉴스 수집
    articles = get_korean_news()
    print(f"📰 총 {len(articles)}개 기사 수집 완료")
    
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
