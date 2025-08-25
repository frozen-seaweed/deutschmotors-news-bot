// api/profile.js
export const config = { runtime: 'nodejs' };

import { getLikesByDay } from '../lib/store.js';
import { buildWeightsFromLikes } from '../lib/recommend.js';

function dayStrKST(offsetDays = 0) {
  const t = Date.now() + 9 * 60 * 60 * 1000 - offsetDays * 24 * 60 * 60 * 1000;
  return new Date(t).toISOString().slice(0, 10); // YYYY-MM-DD
}

export default async function handler(req, res) {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const userId = url.searchParams.get('userId') || 'test';
    const days = Math.max(1, Math.min(30, Number(url.searchParams.get('days') || 14)));
    const topN = Math.max(1, Math.min(50, Number(url.searchParams.get('top') || 20)));

    // 최근 N일 좋아요 모으기
    const liked = [];
    for (let i = 0; i < days; i++) {
      const d = dayStrKST(i);
      const items = await getLikesByDay({ userId, dayKST: d });
      liked.push(...items);
    }

    // 가중치 학습
    const weights = buildWeightsFromLikes(liked);
    const rankedTokens = Object.entries(weights)
      .sort((a, b) => b[1] - a[1])
      .slice(0, topN)
      .map(([token, weight]) => ({ token, weight }));

    return res.status(200).json({
      userId,
      daysCollected: days,
      likeCount: liked.length,
      topTokens: rankedTokens
    });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
