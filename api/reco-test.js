// api/reco-test.js
export const config = { runtime: 'nodejs' };

import { saveLike, getLikesByDay } from '../lib/store.js';
import { buildWeightsFromLikes, scoreArticles } from '../lib/recommend.js';

function todayKST() {
  const now = Date.now() + 9 * 60 * 60 * 1000; // UTC→KST
  return new Date(now).toISOString().slice(0, 10); // YYYY-MM-DD
}

export default async function handler(req, res) {
  try {
    const url = new URL(req.url, `http://${req.headers.host}`);
    const userId = url.searchParams.get('userId') || 'test';
    const dayKST = url.searchParams.get('day') || todayKST();
    const seed = url.searchParams.get('seed') === '1';

    // seed=1이면 테스트용 좋아요 3개를 저장해서 바로 확인 가능
    if (seed) {
      const samples = [
        { title: '현대차 전기차 전략 발표', summary: '배터리 효율 개선' },
        { title: 'AI 반도체 시장 급성장', summary: '고성능 칩 수요 확대' },
        { title: '테슬라 가격 인하 이슈', summary: '전기차 판매 촉진' }
      ];
      for (const a of samples) {
        await saveLike({ userId, dayKST, article: a });
      }
    }

    // 1) 좋아요 불러오기 → 2) 가중치 학습 → 3) 새 기사 후보 점수화
    const likes = await getLikesByDay({ userId, dayKST });
    const weights = buildWeightsFromLikes(likes);

    // 데모용 후보 기사 4개
    const candidates = [
      { title: '전기차 판매 급증', summary: '배터리 원가 하락' },
      { title: '국내 증시 상승세', summary: '은행주 강세' },
      { title: 'AI 반도체 수요 폭발', summary: '칩 공급난' },
      { title: '신형 SUV 출시', summary: '가솔린 모델 강화' }
    ];
    const ranked = scoreArticles(candidates, weights);

    return res.status(200).json({
      userId,
      dayKST,
      likeCount: likes.length,
      topRanks: ranked.slice(0, 4)
    });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}

