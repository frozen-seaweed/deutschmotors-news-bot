# api/index.py - Vercel 호환형 Webhook 처리
import json
import os
import base64
import re
import requests
from datetime import datetime

def handler(request):
    try:
        if request["method"] == "GET":
            return get_status_page()

        elif request["method"] == "POST":
            path = request["url"]
            if path.endswith("/api/webhook"):
                return handle_webhook(json.loads(request["body"]))

        return {
            "statusCode": 404,
            "body": "Not Found"
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Error: {str(e)}"
        }

def get_status_page():
    preferences = load_preferences()
    html = f"""
    <h1>🤖 DeutschMotors News Bot</h1>
    <h2>Webhook 상태</h2>
    <p><strong>상태:</strong> 🟢 실행 중</p>
    <p><strong>현재 시간:</strong> {datetime.now().isoformat()}</p>
    <p><strong>총 좋아요:</strong> {preferences.get('total_likes', 0)}개</p>
    <p><strong>학습된 키워드:</strong> {len(preferences.get('liked_keywords', {}))}개</p>
    <hr><p><em>텔레그램 좋아요 처리용</em></p>
    """
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": html
    }

def handle_webhook(data):
    if 'callback_query' in data:
        callback = data['callback_query']
        user_id = callback['from']['id']
        chat_id = callback['message']['chat']['id']
        message_text = callback['message']['text']
        callback_data = callback['data']
        article_title = extract_article_title(message_text)
        if not article_title:
            return {"statusCode": 200, "body": "no title"}

        preferences = update_user_preferences(article_title, callback_data.startswith('like_'))
        push_to_github(preferences)
        send_feedback(chat_id, article_title, callback_data.startswith('like_'))
        answer_callback(callback['id'])
        return {"statusCode": 200, "body": "ok"}
    else:
        return {"statusCode": 200, "body": "noop"}

def extract_article_title(text):
    lines = text.split('\n')
    for line in lines:
        if line.startswith('*📰'):
            title = line.replace('*📰', '').replace('*', '').strip()
            title = re.sub(r'^\d+\.\s*', '', title)
            return title
    return ""

def extract_keywords(title):
    keywords = []
    patterns = [
        r'현대(?:차|모터스)?', r'기아(?:차)?', r'제네시스', r'테슬라', r'BMW', r'벤츠', r'아우디',
        r'전기차', r'EV', r'하이브리드', r'수소차', r'배터리', r'충전(?:소|기)?',
        r'SUV', r'세단', r'모빌리티', r'자율주행', r'카셰어링',
        r'딜러(?:사|십)?', r'중고차', r'리스', r'렌트',
        r'모델[YS3X]?', r'아이오닉', r'쏘나타', r'아반떼', r'그랜저'
    ]
    for pattern in patterns:
        matches = re.findall(pattern, title, re.IGNORECASE)
        keywords.extend(matches)
    words = re.findall(r'[가-힣a-zA-Z]{2,}', title)
    for w in words:
        if w not in ['기사', '뉴스', '관련', '발표', '출시', '판매']:
            keywords.append(w)
    return list(set(keywords))[:5]

def load_preferences():
    try:
        token = os.environ.get("GITHUB_TOKEN")
        repo = os.environ.get("GITHUB_REPO")
        
        print(f"🔧 GITHUB_TOKEN: {token}")
        print(f"🔧 GITHUB_REPO: {repo}")

        url = f"https://api.github.com/repos/{repo}/contents/user_preferences.json"
        headers = {"Authorization": f"token {token}"}
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            content = base64.b64decode(r.json()["content"]).decode()
            return json.loads(content)
    except:
        pass
    return {"liked_keywords": {}, "total_likes": 0, "last_updated": "", "last_cleanup": ""}

def update_user_preferences(title, is_like):
    prefs = load_preferences()
    keywords = extract_keywords(title)
    liked = prefs.get("liked_keywords", {})
    for kw in keywords:
        if is_like:
            liked[kw] = liked.get(kw, 0) + 1
        else:
            if kw in liked:
                liked[kw] = max(0, liked[kw] - 1)
                if liked[kw] == 0:
                    del liked[kw]
    prefs["liked_keywords"] = liked
    if is_like:
        prefs["total_likes"] = prefs.get("total_likes", 0) + 1
    prefs["last_updated"] = datetime.now().isoformat()
    return prefs

def push_to_github(prefs):
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    url = f"https://api.github.com/repos/{repo}/contents/user_preferences.json"
    headers = {"Authorization": f"token {token}"}
    get_res = requests.get(url, headers=headers)
    if get_res.status_code == 200:
        sha = get_res.json()["sha"]
    else:
        sha = None
    content = base64.b64encode(json.dumps(prefs, ensure_ascii=False, indent=2).encode()).decode()
    data = {
        "message": f"Update {datetime.now().isoformat()}",
        "content": content
    }
    if sha:
        data["sha"] = sha
    requests.put(url, headers=headers, json=data)

def send_feedback(chat_id, title, is_like):
    msg = f"👍 '{title[:30]}...' 뉴스 반영됨!" if is_like else f"👎 '{title[:30]}...' 뉴스 줄임!"
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": msg})

def answer_callback(cb_id):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    requests.post(url, json={"callback_query_id": cb_id})
