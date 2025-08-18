# storage.py
import os, json, base64, requests
from datetime import datetime, timedelta

# 환경변수: GitHub Actions / Vercel에서 세팅
REPO = os.environ.get("GITHUB_REPO")  # 예: "frozen-seaweed/deutschmotors-news-bot"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

HEADERS = {
    "Authorization": f"token {TOKEN}" if TOKEN else "",
    "Accept": "application/vnd.github+json",
}

# 파일 경로들 (레포 루트에 저장)
PREF_PATH = "user_preferences.json"   # webhook.js가 업데이트 중
SENT_PATH = "sent_articles.json"      # 우리가 보낸 기사 기록 (여기에 새로 저장)
# (참고) 기존 liked_articles.json은 더 이상 사용하지 않습니다.

def _get_from_github(path):
    """레포의 파일(JSON)을 읽어옴: (data, sha) 반환. 없으면 ({}, None)"""
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code == 200:
        j = r.json()
        content = base64.b64decode(j["content"]).decode("utf-8")
        return json.loads(content), j.get("sha")
    return {}, None

def _put_to_github(path, data, sha=None, message="update"):
    """레포에 파일(JSON) 저장 (create/update)"""
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")
    body = {"message": f"{message} {datetime.utcnow().isoformat()}Z", "content": content}
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=HEADERS, json=body, timeout=15)
    r.raise_for_status()
    return r.json()

# ---------- 학습 키워드 읽기 ----------
def build_keyword_weights():
    """
    webhook.js가 유지하는 user_preferences.json에서
    liked_keywords를 읽어와 점수 딕셔너리로 반환.
    없으면 빈 dict.
    """
    data, _ = _get_from_github(PREF_PATH)
    liked = data.get("liked_keywords", {}) if isinstance(data, dict) else {}
    # 예: {"테슬라": 3, "배터리": 5, ...}
    return liked

# ---------- 보낸 기사 기록 ----------
def load_sent_articles(days_to_keep=7):
    """
    sent_articles.json을 읽어 dict(url -> ISO시간) 반환.
    7일 지난 기록은 자동 정리.
    """
    data, sha = _get_from_github(SENT_PATH)
    if not isinstance(data, dict):
        data = {}
    cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
    cleaned = {}
    for url, ts in data.items():
        try:
            dt = datetime.fromisoformat(ts.replace("Z", ""))
            if dt > cutoff:
                cleaned[url] = ts
        except Exception:
            # 파싱 실패해도 남겨둠
            cleaned[url] = ts
    return cleaned, sha

def save_sent_articles(data, sha=None):
    """보낸 기사 기록을 깃허브에 저장"""
    return _put_to_github(SENT_PATH, data, sha, message="update sent_articles")
