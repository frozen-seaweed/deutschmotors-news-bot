import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta

LIKED_FILE = "liked_articles.json"

def store_liked_article(url, title, description):
    """좋아요 누른 뉴스 저장"""
    if os.path.exists(LIKED_FILE):
        with open(LIKED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = []

    # 중복 방지
    if any(d['url'] == url for d in data):
        return

    data.append({
        "url": url,
        "title": title,
        "description": description,
        "timestamp": datetime.now().isoformat()
    })

    with open(LIKED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def build_keyword_weights():
    """좋아요한 뉴스 기반 키워드 점수 계산"""
    if not os.path.exists(LIKED_FILE):
        return {}

    with open(LIKED_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    words = []
    for item in data:
        text = f"{item['title']} {item['description']}".lower()
        text = re.sub(r'[^가-힣a-zA-Z0-9\s]', '', text)
        words.extend(text.split())

    stopwords = {'이', '그', '저', '은', '는', '에', '의', '가', '을', '를', '에서', '으로', '하다', '했다', '있는', '그리고'}
    keywords = [word for word in words if word not in stopwords and len(word) > 1]

    return dict(Counter(keywords))

def score_article(article, keyword_weights):
    """뉴스 기사 점수 계산"""
    text = f"{article['title']} {article.get('description', '')}".lower()
    score = 0
    for keyword, weight in keyword_weights.items():
        if keyword in text:
            score += weight
    return score
