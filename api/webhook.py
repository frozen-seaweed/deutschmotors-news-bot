# api/webhook.py - Vercel Serverless Function
from http.server import BaseHTTPRequestHandler
import json
import os
import requests
from datetime import datetime
import re
import base64

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """GET 요청 처리 - 서버 상태 확인"""
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            preferences = self.load_preferences()
            status_html = f"""
            <h1>🤖 DeutschMotors News Bot</h1>
            <h2>웹훅 서버 상태</h2>
            <p><strong>상태:</strong> 🟢 Vercel에서 실행 중</p>
            <p><strong>현재 시간:</strong> {datetime.now().isoformat()}</p>
            <p><strong>총 좋아요:</strong> {preferences.get('total_likes', 0)}개</p>
            <p><strong>학습된 키워드:</strong> {len(preferences.get('liked_keywords', {}))}개</p>
            <h3>인기 키워드 TOP 5</h3>
            <ul>
            {''.join([f'<li>{k}: {v}점</li>' for k, v in sorted(preferences.get('liked_keywords', {}).items(), key=lambda x: x[1], reverse=True)[:5]])}
            </ul>
            <hr>
            <p><em>이 서버는 텔레그램 좋아요 버튼을 처리합니다.</em></p>
            """
            self.wfile.write(status_html.encode())
            
        elif self.path == '/api/stats':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            preferences = self.load_preferences()
            stats = {
                'total_likes': preferences.get('total_likes', 0),
                'keywords_count': len(preferences.get('liked_keywords', {})),
                'top_keywords': dict(sorted(
                    preferences.get('liked_keywords', {}).items(), 
                    key=lambda x: x[1], 
                    reverse=True
                )[:10]),
                'last_updated': preferences.get('last_updated', 'Unknown')
            }
            self.wfile.write(json.dumps(stats).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """POST 요청 처리 - 텔레그램 웹훅"""
        if self.path == '/api/webhook':
            try:
                # 요청 데이터 읽기
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                # 콜백 쿼리 처리 (좋아요 버튼 클릭)
                if 'callback_query' in data:
                    result = self.handle_callback_query(data['callback_query'])
                    
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode())
                else:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'status': 'ok'}).encode())
                    
            except Exception as e:
                print(f"웹훅 처리 오류: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'error', 'message': str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def handle_callback_query(self, callback):
        """좋아요/싫어요 버튼 처리"""
        try:
            user_id = callback['from']['id']
            chat_id = callback['message']['chat']['id']
            callback_data = callback['data']
            message_text = callback['message']['text']
            
            print(f"🔔 콜백 수신: {callback_data}")
            
            # 좋아요/싫어요 처리
            if callback_data.startswith('like_') or callback_data.startswith('dislike_'):
                is_like = callback_data.startswith('like_')
                
                # 메시지에서 기사 제목 추출
                article_title = self.extract_article_title(message_text)
                
                if article_title:
                    # 취향 업데이트
                    preferences = self.update_user_preferences(article_title, is_like)
                    
                    # GitHub에 업데이트
                    self.push_to_github(preferences)
                    
                    # 사용자에게 피드백
                    if is_like:
                        feedback = f"👍 좋아요 반영됨!\n'{article_title[:30]}...' 스타일의 뉴스를 더 찾아드릴게요."
                    else:
                        feedback = f"👎 취향 반영됨!\n'{article_title[:30]}...' 스타일은 줄여드릴게요."
                    
                    # 콜백 응답
                    self.answer_callback_query(callback['id'])
                    
                    # 피드백 메시지 전송
                    self.send_telegram_message(chat_id, feedback)
                    
                    return {'status': 'success'}
            
            return {'status': 'ok'}
            
        except Exception as e:
            print(f"콜백 처리 오류: {e}")
            return {'status': 'error', 'message': str(e)}

    def extract_article_title(self, message_text):
        """메시지에서 기사 제목 추출"""
        lines = message_text.split('\n')
        for line in lines:
            if line.startswith('*📰'):
                title = line.replace('*📰', '').replace('*', '').strip()
                # 숫자와 점 제거
                title = re.sub(r'^\d+\.\s*', '', title)
                return title
        return ""

    def extract_keywords_from_title(self, title):
        """기사 제목에서 키워드 추출"""
        keywords = []
        
        # 자동차 관련 키워드 패턴
        auto_patterns = [
            r'현대(?:차|모터스)?', r'기아(?:차)?', r'제네시스', r'테슬라', r'BMW', r'벤츠', r'아우디',
            r'전기차', r'EV', r'하이브리드', r'수소차', r'배터리', r'충전(?:소|기)?',
            r'SUV', r'세단', r'모빌리티', r'자율주행', r'카셰어링',
            r'딜러(?:사|십)?', r'중고차', r'리스', r'렌트',
            r'모델[YS3X]?', r'아이오닉', r'쏘나타', r'아반떼', r'그랜저'
        ]
        
        for pattern in auto_patterns:
            matches = re.findall(pattern, title, re.IGNORECASE)
            keywords.extend([match for match in matches if len(match) >= 2])
        
        # 일반적인 단어들도 추출
        words = re.findall(r'[가-힣a-zA-Z]{2,}', title)
        for word in words:
            if word not in ['기사', '뉴스', '관련', '발표', '출시', '판매']:
                keywords.append(word)
        
        # 중복 제거 및 정리
        unique_keywords = list(set([kw.strip() for kw in keywords if len(kw.strip()) >= 2]))
        
        return unique_keywords[:5]

    def load_preferences(self):
        """GitHub에서 취향 데이터 로드"""
        try:
            github_token = os.environ.get('GITHUB_TOKEN')
            github_repo = os.environ.get('GITHUB_REPO')
            
            if not github_token or not github_repo:
                return self.get_default_preferences()
            
            url = f"https://api.github.com/repos/{github_repo}/contents/user_preferences.json"
            headers = {
                'Authorization': f'token {github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            response = requests.get(url, headers=headers)
            
            if response.status_code == 200:
                content = response.json()['content']
                decoded_content = base64.b64decode(content).decode('utf-8')
                return json.loads(decoded_content)
            else:
                return self.get_default_preferences()
                
        except Exception as e:
            print(f"취향 데이터 로드 오류: {e}")
            return self.get_default_preferences()

    def get_default_preferences(self):
        """기본 취향 데이터"""
        return {
            "liked_keywords": {},
            "last_cleanup": datetime.now().strftime('%Y-%m-%d'),
            "total_likes": 0,
            "last_updated": datetime.now().isoformat()
        }

    def update_user_preferences(self, article_title, is_like=True):
        """사용자 취향 업데이트"""
        preferences = self.load_preferences()
        preferences = self.cleanup_old_data(preferences)
        
        # 기사 제목에서 키워드 추출
        keywords = self.extract_keywords_from_title(article_title)
        
        if not keywords:
            return preferences
        
        liked_keywords = preferences.get('liked_keywords', {})
        
        for keyword in keywords:
            if is_like:
                # 좋아요: 점수 증가
                liked_keywords[keyword] = liked_keywords.get(keyword, 0) + 1
                print(f"👍 키워드 '{keyword}' 점수 증가: {liked_keywords[keyword]}")
            else:
                # 싫어요: 점수 감소
                if keyword in liked_keywords:
                    liked_keywords[keyword] = max(0, liked_keywords[keyword] - 1)
                    if liked_keywords[keyword] == 0:
                        del liked_keywords[keyword]
                    print(f"👎 키워드 '{keyword}' 점수 감소: {liked_keywords.get(keyword, 0)}")
        
        preferences['liked_keywords'] = liked_keywords
        if is_like:
            preferences['total_likes'] = preferences.get('total_likes', 0) + 1
        
        return preferences

    def cleanup_old_data(self, preferences):
        """30일 지난 데이터 정리"""
        try:
            last_cleanup = datetime.fromisoformat(preferences.get('last_cleanup', datetime.now().isoformat()))
            now = datetime.now()
            
            # 30일마다 데이터 리셋
            if (now - last_cleanup).days >= 30:
                print("🧹 30일 지난 취향 데이터 정리 중...")
                preferences['liked_keywords'] = {}
                preferences['last_cleanup'] = now.strftime('%Y-%m-%d')
                preferences['total_likes'] = 0
                print("✅ 취향 데이터 정리 완료")
                
            return preferences
        except Exception as e:
            print(f"데이터 정리 오류: {e}")
            return preferences

    def push_to_github(self, preferences):
        """GitHub 저장소에 취향 파일 업데이트"""
        try:
            github_token = os.environ.get('GITHUB_TOKEN')
            github_repo = os.environ.get('GITHUB_REPO')
            
            if not github_token or not github_repo:
                print("⚠️  GitHub 설정이 없어서 업데이트하지 않습니다.")
                return False
            
            url = f"https://api.github.com/repos/{github_repo}/contents/user_preferences.json"
            headers = {
                'Authorization': f'token {github_token}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # 현재 파일의 SHA 가져오기
            get_response = requests.get(url, headers=headers)
            
            preferences['last_updated'] = datetime.now().isoformat()
            file_content = json.dumps(preferences, ensure_ascii=False, indent=2)
            encoded_content = base64.b64encode(file_content.encode('utf-8')).decode('utf-8')
            
            data = {
                'message': f'🤖 취향 데이터 업데이트 - {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                'content': encoded_content
            }
            
            if get_response.status_code == 200:
                data['sha'] = get_response.json()['sha']
            
            response = requests.put(url, headers=headers, json=data)
            
            if response.status_code in [200, 201]:
                print("✅ GitHub에 취향 데이터 업데이트 성공!")
                return True
            else:
                print(f"❌ GitHub 업데이트 실패: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ GitHub 업데이트 오류: {e}")
            return False

    def answer_callback_query(self, callback_query_id):
        """콜백 쿼리 응답"""
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
        data = {
            'callback_query_id': callback_query_id,
            'text': '✅ 취향이 반영되었습니다!',
            'show_alert': False
        }
        requests.post(url, json=data)

    def send_telegram_message(self, chat_id, text):
        """텔레그램 메시지 전송"""
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
        
        try:
            response = requests.post(url, json=data)
            return response.json().get('ok', False)
        except Exception as e:
            print(f"텔레그램 메시지 전송 오류: {e}")
            return False
