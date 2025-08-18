# storage.py
import os, json, base64, requests, re
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

REPO = os.environ.get("GITHUB_REPO")  # 예: "frozen-seaweed/deutschmotors-news-bot"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

HEADERS = {
    "Authorization": f"token {TOKEN}" if TOKEN else "",
    "Accept": "application/vnd.github+json",
}

PREF_PATH = "user_preferences.json"   # (webhook.js가 업데이트하는 파일)
SENT_PATH = "sent_articles.json"      # (우리가 보낸 기사 기록 저장)

# ---- URL 정규화(중복 제거의 핵심): 추적 파라미터 제거, 소문자, 슬래시/프래그먼트 정리
_DROP_QUERY_PREFIXES = ("utm_", "gclid", "fbclid")
def normalize_url(url: str) -> str:
    try:
        u = urlparse(url.strip())
        qs = [
            (k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
            if not any(k.lower().startswith(p) for p in _DROP_QUERY_PREFIXES)
        ]
        clean = u._replace(
            scheme=u.scheme.lower(),
            netloc=u.netloc.lower(),
            path=(u.path or "").rstrip("/"),
            query=urlencode(qs, doseq=True),
            fragment=""
        )
        return urlunparse(clean)
    except Exception:
        return (url or "").strip()

def _get_from_github(path):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    r = requests.get(url, headers=HEADERS, timeout=20)
    if r.status_code == 200:
        j = r.json()
        content = base64.b64decode(j["content"]).decode("utf-8")
        return json.loads(content), j.get("sha")
    return {}, None

def _put_to_github(path, data, sha=None, message="update"):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    content = base64.b64encode(
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("utf-8")
    body = {"message": f"{message} {datetime.utcnow().isoformat()}Z", "content": content}
    if sha:
        body["sha"] = sha
    r = requests.put(url, headers=HEADERS, json=body, timeout=20)
    r.raise_for_status()
    return r.json()

# ---- 좋아요 학습 키워드 (webhook.js가 유지)
def build_keyword_weights():
    data, _ = _get_from_github(PREF_PATH)
    liked = data.get("liked_keywords", {}) if isinstance(data, dict) else {}
    return liked

# ---- 보낸 기사 기록
def load_sent_articles(days_to_keep=7):
    data, sha = _get_from_github(SENT_PATH)
    if not isinstance(data, dict):
        data = {}
    cutoff = datetime.utcnow() - timedelta(days=7)
    cleaned = {}
    for url, ts in data.items():
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", ""))
            if dt > cutoff:
                cleaned[url] = ts
        except Exception:
            cleaned[url] = ts
    return cleaned, sha

def save_sent_articles(data, sha=None):
    return _put_to_github(SENT_PATH, data, sha, message="update sent_articles")
