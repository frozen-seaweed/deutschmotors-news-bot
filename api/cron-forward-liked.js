// api/cron-forward-liked.js
export const config = { runtime: 'nodejs' };

import { getAllLikesByDay } from '../lib/store.js';

const BOT = process.env.TELEGRAM_BOT_TOKEN;
const FWD_CHANNEL_ID = process.env.FWD_CHANNEL_ID; // 다른 채널의 chat_id (예: -100xxxxxxxxxx)

function yesterdayKST() {
  const nowKST = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const y = new Date(nowKST.getTime() - 24 * 60 * 60 * 1000);
  return y.toISOString().slice(0, 10); // YYYY-MM-DD
}

function normKey(a) {
  const t = (a.title || '').toLowerCase().trim().replace(/\s+/g, ' ');
  const u = (a.url || '').toLowerCase().trim();
  return u || t; // url 우선, 없으면 제목
}

async function tgSend(chatId, text) {
  const api = `https://api.telegram.org/bot${BOT}/sendMessage`;
  const body = {
    chat_id: chatId,
    text,
    parse_mode: 'HTML',
    disable_web_page_preview: false
  };
  const r = await fetch(api, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!j.ok) throw new Error(`Telegram send failed: ${JSON.stringify(j)}`);
  return j;
}

export default async function handler(req, res) {
  try {
    if (!BOT || !FWD_CHANNEL_ID) {
      return res.status(500).json({ ok: false, error: 'Missing TELEGRAM_BOT_TOKEN or FWD_CHANNEL_ID' });
    }

    const day = yesterdayKST();
    const items = await getAllLikesByDay(day); // 전날(KST) 모든 사용자 좋아요

    if (!items.length) {
      // 좋아요가 하나도 없으면 조용히 통과하거나 안내 메시지 1건만 전송
      await tgSend(FWD_CHANNEL_ID, `📭 어제(${day} KST)는 좋아요된 뉴스가 없었습니다.`);
      return res.status(200).json({ ok: true, sent: 1, day, note: 'no likes' });
    }

    // 같은 기사(제목/URL) 묶어서 집계
    const map = new Map();
    for (const a of items) {
      const key = normKey(a);
      if (!key) continue;
      const cur = map.get(key) || { article: a, count: 0 };
      cur.count += 1;
      // 최초 저장된 article을 유지(가장 온전한 제목/URL)
      if (!cur.article.title && a.title) cur.article.title = a.title;
      if (!cur.article.url && a.url) cur.article.url = a.url;
      map.set(key, cur);
    }

    // 좋아요 수 내림차순 상위 4개
    const top = Array.from(map.values())
      .sort((x, y) => y.count - x.count)
      .slice(0, 4);

    // 헤더 안내
    await tgSend(FWD_CHANNEL_ID, `📌 어제(${day} KST) DT 채널 좋아요 TOP 4`);

    // 개별 기사 전송
    let sent = 1;
    for (const { article, count } of top) {
      const title = article.title || '제목 없음';
      const url = article.url ? `\n${article.url}` : '';
      await tgSend(FWD_CHANNEL_ID, `👍 ${count} • ${title}${url}`);
      sent += 1;
    }

    return res.status(200).json({ ok: true, day, totalLikes: items.length, sent, top });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
