// api/webhook.js
// Vercel Node.js Serverless Function – Telegram webhook + GitHub 저장 + 상태 페이지

// ── 도우미: 환경변수
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
const GITHUB_REPO = process.env.GITHUB_REPO; // 예: "frozen-seaweed/deutschmotors-news-bot"

function ensureEnv(res) {
  const missing = [];
  if (!TELEGRAM_BOT_TOKEN) missing.push("TELEGRAM_BOT_TOKEN");
  if (!GITHUB_TOKEN) missing.push("GITHUB_TOKEN");
  if (!GITHUB_REPO) missing.push("GITHUB_REPO");
  if (missing.length) {
    res
      .status(500)
      .send("Missing env: " + missing.join(", ") + " (Vercel Project Settings에서 등록)");
    return false;
  }
  return true;
}

// ── 도우미: GitHub Contents API
async function loadPreferences() {
  const url = `https://api.github.com/repos/${GITHUB_REPO}/contents/user_preferences.json`;
  const r = await fetch(url, {
    headers: { Authorization: `token ${GITHUB_TOKEN}`, Accept: "application/vnd.github+json" },
  });

  if (r.status === 200) {
    const j = await r.json();
    const content = Buffer.from(j.content, "base64").toString("utf8");
    return { data: JSON.parse(content), sha: j.sha };
  }

  // 파일이 없거나 에러면 기본값
  return {
    data: {
      liked_keywords: {},
      total_likes: 0,
      last_updated: "",
      last_cleanup: "",
    },
    sha: null,
  };
}

async function savePreferences(prefs, sha = null) {
  const url = `https://api.github.com/repos/${GITHUB_REPO}/contents/user_preferences.json`;
  const content = Buffer.from(JSON.stringify(prefs, null, 2), "utf8").toString("base64");
  const body = {
    message: `Update preferences ${new Date().toISOString()}`,
    content,
  };
  if (sha) body.sha = sha;

  const r = await fetch(url, {
    method: "PUT",
    headers: {
      Authorization: `token ${GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (r.status !== 200 && r.status !== 201) {
    const txt = await r.text();
    throw new Error(`GitHub save failed: ${r.status} ${txt}`);
  }
}

function extractTitleFromMessageText(text = "") {
  // 메시지에서 제목 라인을 찾아 깨끗한 제목 문자열을 반환
  // 허용: '*📰', '📰', '*✅', '✅' 로 시작하는 줄. 그래도 없으면 첫 번째 비어있지 않은 줄.
  const lines = (text || "").split("\n").map((l) => l.trim()).filter(Boolean);

  let line =
    lines.find((l) => l.startsWith("*📰") || l.startsWith("📰")) ??
    lines.find((l) => l.startsWith("*✅") || l.startsWith("✅")) ??
    lines[0] ??
    "";

  // 선행 기호 제거: 별표/이모지/번호
  line = line
    .replace(/^\*+/, "")        // 선행 별표 제거
    .replace(/^[📰✅]\s*/, "")  // 선행 이모지 제거
    .replace(/^([0-9]+)\.\s*/, "") // "1. " 같은 번호 제거
    .trim();

  return line;
}


function extractKeywords(title = "") {
  const patterns = [
    /현대(?:차|모터스)?/gi,
    /기아(?:차)?/gi,
    /제네시스/gi,
    /테슬라/gi,
    /BMW/gi,
    /벤츠/gi,
    /아우디/gi,
    /전기차|EV/gi,
    /하이브리드/gi,
    /수소차/gi,
    /배터리/gi,
    /충전(?:소|기)?/gi,
    /SUV|세단/gi,
    /모빌리티/gi,
    /자율주행/gi,
    /카셰어링/gi,
    /딜러(?:사|십)?/gi,
    /중고차/gi,
    /리스|렌트/gi,
    /아이오닉|쏘나타|아반떼|그랜저/gi,
  ];
  let found = new Set();
  for (const re of patterns) {
    const m = title.match(re);
    if (m) for (const t of m) found.add(t.toLowerCase());
  }
  // 너무 일반적인 단어 정리
  const stop = new Set(["뉴스", "속보", "브리핑"]);
  found = new Set([...found].filter((t) => !stop.has(t)));
  return [...found];
}

function updatePreferencesObject(prefs, keywords = [], isLike = true) {
  prefs = prefs || {};
  const liked = prefs.liked_keywords || {};
  // 점수 조정: 좋아요 +1, 싫어요 -1, 0 이하면 삭제
  for (const kw of keywords) {
    if (!kw) continue;
    if (isLike) {
      liked[kw] = (liked[kw] || 0) + 1;
    } else {
      if (liked[kw]) {
        liked[kw] = Math.max(0, liked[kw] - 1);
        if (liked[kw] === 0) delete liked[kw];
      }
    }
  }
  prefs.liked_keywords = liked;
  if (isLike) prefs.total_likes = (prefs.total_likes || 0) + 1;
  prefs.last_updated = new Date().toISOString();
  return prefs;
}

// ── 도우미: 텔레그램 응답
async function tgAnswerCallback(id, text = "✅ 취향이 반영되었습니다!") {
  const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/answerCallbackQuery`;
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ callback_query_id: id, text, show_alert: false }),
  });
}
async function tgSendMessage(chatId, text) {
  const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
}

// ── 상태 페이지 (GET)
async function statusHtml() {
  const { data } = await loadPreferences();
  const liked = data.liked_keywords || {};
  const top = Object.entries(liked)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([k, v]) => `<li>${k}: ${v}점</li>`)
    .join("");

  return `
  <html><head><meta charset="utf-8"><title>Webhook Status</title></head>
  <body style="font-family:system-ui,Segoe UI,Apple SD Gothic Neo,sans-serif;line-height:1.5;padding:24px">
    <h1>Telegram Webhook</h1>
    <p>선호 키워드 상위 10</p>
    <ol>${top}</ol>
    <hr/>
    <p style="color:#666">이 엔드포인트는 텔레그램 좋아요 콜백(Webhook)을 처리합니다.</p>
  </body></html>`;
}

// ── 메인 핸들러
export default async function handler(req, res) {
  try {
    if (!ensureEnv(res)) return;

    if (req.method === "GET") {
      const html = await statusHtml();
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      return res.status(200).send(html);
    }

    if (req.method !== "POST") {
      return res.status(405).send("Method Not Allowed");
    }

    // Telegram Webhook 바디
    const update = typeof req.body === "string" ? JSON.parse(req.body) : req.body;
    if (!update) return res.status(200).json({ ok: true, note: "empty body" });

    // Callback Query(좋아요/싫어요 버튼) 처리
    if (update.callback_query) {
      const cb = update.callback_query;
      const data = (cb.data || "").toLowerCase().trim();
      const isLike = /^like\b/.test(data); // 'like', 'LIKE:xxxx' 등 허용
      const chatId = cb.message?.chat?.id;
      const title = extractTitleFromMessageText(cb.message?.text || "");

      // 키워드 추출 & 선호도 업데이트
      const { data: prefs, sha } = await loadPreferences();
      const keywords = extractKeywords(title);
      const updated = updatePreferencesObject(prefs, keywords, isLike);
      await savePreferences(updated, sha);

      // 사용자 응답
      await tgAnswerCallback(cb.id);
      if (chatId) {
        const shortTitle = title ? `'${title.slice(0, 30)}...'` : "이 뉴스";
        const msg = isLike
          ? `👍 ${shortTitle} 반영됨! 비슷한 뉴스 더 보여드릴게요.`
          : `👎 ${shortTitle} 줄일게요.`;
        await tgSendMessage(chatId, msg);
      }
      return res.status(200).json({ ok: true });
    }

    // 그 외 업데이트는 무시
    return res.status(200).json({ ok: true, note: "no callback_query" });
  } catch (err) {
    console.error("❌ webhook error:", err);
    return res.status(500).json({ error: "Internal Server Error" });
  }
}
