// api/train.js
export const config = { runtime: 'nodejs' };

import { getLikesByDay, saveUserProfile } from '../lib/store.js';
import { buildWeightsFromLikes } from '../lib/recommend.js';

function dayStrKST(offset = 0) {
  const t = Date.now() + 9 * 60 * 60 * 1000 - offset * 24 * 60 * 60 * 1000;
  return new Date(t).toISOString().slice(0, 10); // YYYY-MM-DD
}

export default async function handler(req, res) {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const userId = url.searchParams.get('userId') || 'test';
    const days = Math.max(1, Math.min(60, Number(url.searchParams.get('days') || 14)));
    const topN = Math.max(1, Math.min(200, Number(url.searchParams.get('top') || 30)));

    // 최근 N일 좋아요 수집
    const liked = [];
    for (let i = 0; i < days; i++) {
      const d = dayStrKST(i);
      const items = await getLikesByDay({ userId, dayKST: d });
      liked.push(...items);
    }

    if (liked.length === 0) {
      return res.status(200).json({ ok: true, userId, likeCount: 0, message: 'no likes to train' });
    }

    // 가중치 학습 후 프로필로 저장
    const weights = buildWeightsFromLikes(liked);
    await saveUserProfile(userId, weights);

    const topTokens = Object.entries(weights)
      .sort((a, b) => b[1] - a[1])
      .slice(0, topN)
      .map(([token, weight]) => ({ token, weight }));

    return res.status(200).json({
      ok: true,
      userId,
      daysCollected: days,
      likeCount: liked.length,
      saved: true,
      topTokens
    });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
