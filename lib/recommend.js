// lib/recommend.js
// 간단한 콘텐츠 기반 추천: 좋아요 기사에서 단어 가중치 학습 → 새 기사 스코어링
const STOP = new Set([
  'the','a','an','and','or','but','in','on','at','to','for','of','with','by','from',
  'is','are','was','were','be','as','it','that','this'
]);

function tokenize(text) {
  return (text || '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter(w => w && !STOP.has(w));
}

// 좋아요된 기사 목록 -> 단어 가중치 { token: weight(0~1) }
export function buildWeightsFromLikes(likedArticles) {
  const w = {};
  for (const a of likedArticles || []) {
    const tokens = tokenize(`${a.title} ${a.summary || ''}`);
    const seen = new Set();
    for (const t of tokens) {
      if (seen.has(t)) continue;
      seen.add(t);
      w[t] = (w[t] || 0) + 1;
    }
  }
  const max = Math.max(1, ...Object.values(w));
  for (const k of Object.keys(w)) w[k] = w[k] / max;
  return w;
}

// 새 기사 후보들에 점수 부여 후 내림차순 정렬
export function scoreArticles(articles, weights) {
  return (articles || [])
    .map(a => {
      const tokens = tokenize(`${a.title} ${a.summary || ''}`);
      const seen = new Set();
      let score = 0;
      for (const t of tokens) {
        if (seen.has(t)) continue;
        seen.add(t);
        score += weights?.[t] || 0;
      }
      return { ...a, _score: score };
    })
    .sort((x, y) => y._score - x._score);
}
