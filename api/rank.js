// api/rank.js
export const config = { runtime: 'nodejs' };

import { getUserProfile, getLikesByDay, saveUserProfile } from '../lib/store.js';
import { buildWeightsFromLikes, scoreArticles } from '../lib/recommend.js';

function dayStrKST(offset = 0) {
  const t = Date.now() + 9 * 60 * 60 * 1000 - offset * 24 * 60 * 60 * 1000;
  return new Date(t).toISOString().slice(0, 10); // YYYY-MM-DD
}

async function collectLikesDays(userId, days) {
  const liked = [];
  for (let i = 0; i < days; i++) {
    const d = dayStrKST(i);
    const items = await getLikesByDay({ userId, dayKST: d });
    liked.push(...items);
  }
  return liked;
}

export default async function handler(req, res) {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const method = req.method || 'GET';

    const userId = url.searchParams.get('userId') || 'test';
    const topN = Math.max(1, Math.min(50, Number(url.searchParams.get('top') || 5)));
    const days = Math.max(1, Math.min(60, Number(url.searchParams.get('days') || 30)));
    const sample = url.searchParams.get('sample') === '1';

    // 1) 후보 기사 수집
    let candidates = [];
    if (method === 'POST') {
      // 요청 본문으로 [{title, summary, url}] 전달 가능
      const bodyText = typeof req.body === 'string' ? req.body : null;
      const body = bodyText ? JSON.parse(bodyText) : req.body;
      candidates = Array.isArray(body?.items) ? body.items : [];
    }
    if (sample || candidates.length === 0) {
      candidates = [
        { title: '전기차 판매 급증', summary: '배터리 원가 하락과 충전 인프라 확대' },
        { title: '국내 증시 상승세', summary: '은행주 강세로 코스피 상승' },
        { title: 'AI 반도체 수요 폭발', summary: '고성능 칩 공급난 지속' },
        { title: '신형 SUV 출시', summary: '가솔린 모델 라인업 강화' }
      ];
    }

    // 2) 사용자 프로필(가중치) 확보
    let weights = await getUserProfile(userId);
    let profileSource = 'saved';
    if (!weights || Object.keys(weights).length === 0) {
      const liked = await collectLikesDays(userId, days);
      weights = buildWeightsFromLikes(liked);
      await saveUserProfile(userId, weights); // 저장해 두면 다음엔 바로 사용
      profileSource = 'built_from_likes';
    }

    // 3) 점수화 + 상위 N개
    const ranked = scoreArticles(candidates, weights).slice(0, topN);

    return res.status(200).json({
      ok: true,
      userId,
      profileSource,
      daysUsed: days,
      candidates: candidates.length,
      top: ranked
    });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
