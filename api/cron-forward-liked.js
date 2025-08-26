// api/cron-forward-liked.js
// 어제(KST) 좋아요 TOP4를 다른 채널로 전달 (문자 인코딩 이슈 방어)

export const config = { runtime: "nodejs" };

import { getAllLikesByDay } from "../lib/store.js";

const BOT = process.env.TELEGRAM_BOT_TOKEN;
const FWD_CHANNEL_ID = process.env.FWD_CHANNEL_ID || process.env.DT_CHANNEL_ID; // 없으면 쿼리로 chatId 지정 가능

// 어제 날짜(한국시간) YYYY-MM-DD
function kstDay(offset = 1) {
  const t = Date.now() + 9 * 3600 * 1000 - offset * 24 * 3600 * 1000;
  return new Date(t).toISOString().slice(0, 10);
}

// 텍스트 정리: 텔레그램이 거부하는 비정상 문자 제거
function sanitize(str = "") {
  // 제어문자(탭/개행/CR 제외) + 잘못된 서로게이트 제거
  return String(str)
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "")
    .replace(/[\uD800-\uDFFF]/g, "")
    .trim();
}

async function tgSend(chatId, text) {
  const url = `https://api.telegram.org/bot${BOT}/sendMessage`;
  const body = {
    chat_id: chatId,
    text: sanitize(text),
    parse_mode: "HTML",
    disable_web_page_preview: false,
  };
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  });
  const j = await r.json();
  if (!j.ok) throw new Error(j.description || "telegram error");
  return j;
}

export default async function handler(req, res) {
  try {
    if (!BOT) return res.status(500).json({ ok: false, error: "Missing TELEGRAM_BOT_TOKEN" });

    const url = new URL(req.url, `http://${req.headers.host}`);
    const chatId = url.searchParams.get("chatId") || FWD_CHANNEL_ID;
    if (!chatId) return res.status(500).json({ ok: false, error: "Missing FWD_CHANNEL_ID or chatId" });

    const day = kstDay(1);
    const liked = await getAllLikesByDay(day);

    if (!liked || liked.length === 0) {
      await tgSend(chatId, `📭 어제(${day}) 좋아요한 기사가 없었습니다.`);
      return res.status(200).json({ ok: true, day, sent: 1, note: "no likes" });
    }

    // 같은 기사(가능하면 url, 없으면 title) 카운팅
    const map = new Map();
    for (const it of liked) {
      const title = sanitize(it?.title || "");
      const urlStr = sanitize(it?.url || "");
      const key = (urlStr || title).toLowerCase();
      if (!key) continue;
      const cur = map.get(key) || { title, url: urlStr, count: 0 };
      cur.count += 1;
      map.set(key, cur);
    }

    const top = [...map.values()].sort((a, b) => b.count - a.count).slice(0, 4);

    // 전송(한 건 실패해도 전체 실패로 처리하지 않음)
    let sent = 0, fail = 0;
    try { await tgSend(chatId, `✅ 어제(${day}) 좋아요 TOP4`); sent++; } catch { fail++; }
    for (const a of top) {
      const line = a.url ? `📰 ${a.title}\n${a.url}` : `📰 ${a.title}`;
      try { await tgSend(chatId, line); sent++; } catch { fail++; }
    }

    return res.status(200).json({ ok: true, day, topCount: top.length, sent, fail });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
