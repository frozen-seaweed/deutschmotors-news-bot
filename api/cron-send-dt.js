// api/cron-send-dt.js
// DT 채널 아침 뉴스 발송: 전날(또는 최근 N일) 좋아요 데이터로 학습 → 오늘 후보 기사 점수 순으로 전송
export const config = { runtime: 'nodejs' };

import { getAllLikesByDay } from '../lib/store.js';
import { buildWeightsFromLikes, scoreArticles } from '../lib/recommend.js';

const BOT = process.env.TELEGRAM_BOT_TOKEN;
const DT_CHANNEL_ID = process.env.DT_CHANNEL_ID;        // DT 채널 chat_id (예: -100xxxxxxxxxx)
const NEWS_SOURCE_URL = process.env.NEWS_SOURCE_URL || ""; // 후보 기사 JSON을 제공하는 URL (없으면 sample=1로 테스트)

function dayStrKST(offset = 0) {
  const t = Date.now() + 9 * 60 * 60 * 1000 - offset * 24 * 60 * 60 * 1000;
  return new Date(t).toISOString().slice(0, 10); // YYYY-MM-DD (KST)
}

async function collectAllLikesDays(days) {
  const liked = [];
  for (let i = 1; i <= days; i++) { // 어제부터 days일
    const d = dayStrKST(i);
    const items = await getAllLikesByDay(d);
    liked.push(...items);
  }
  return liked;
}

async function tgSend(chatId, text) {
  const api = `https://api.telegram.org/bot${BOT}/sendMessage`;
  const body = { chat_id: chatId, text, parse_mode: 'HTML', disable_web_page_preview: false };
  const r = await fetch(api, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!j.ok) throw new Error(`Telegram send failed: ${JSON.stringify(j)}`);
  return j;
}

async function loadCandidates(sample) {
  // 1) 외부 URL에서 JSON 로드 (배열 또는 {items:[...]} 둘 다 지원)
  if (!sample && NEWS_SOURCE_URL) {
    try {
      const r = await fetch(NEWS_SOURCE_URL, { headers: { 'Accept': 'application/json' } });
      const j = await r.json();
      const arr = Array.isArray(j) ? j : (Array.isArray(j?.items) ? j.items : []);
      // 각 항목은 {title, summary, url} 형식이면 충분
      if (arr.length) return arr.map(x => ({
        title: x.title || x.headline || '',
        summary: x.summary || x.description || '',
        url: x.url || x.link || ''
      }));
    } catch (e) {
      // 무시하고 샘플로 진행
    }
  }
  // 2) 샘플 후보 (테스트용)
  return [
    { title: '전기차 판매 급증', summary: '배터리 원가 하락과 충전 인프라 확대', url: 'https://example.com/ev-sales' },
    { title: '국내 증시 상승세', summary: '은행주 강세로 코스피 상승', url: 'https://example.com/kospi' },
    { title: 'AI 반도체 수요 폭발', summary: '고성능 칩 공급난 지속', url: 'https://example.com/ai-chip' },
    { title: '신형 SUV 출시', summary: '가솔린 모델 라인업 강화', url: 'https://example.com/new-suv' }
  ];
}

export default async function handler(req, res) {
  try {
    if (!BOT || !DT_CHANNEL_ID) {
      return res.status(500).json({ ok: false, error: 'Missing TELEGRAM_BOT_TOKEN or DT_CHANNEL_ID' });
    }

    const url = new URL(req.url, `http://${req.headers.host}`);
    const days = Math.max(1, Math.min(60, Number(url.searchParams.get('days') || 30))); // 학습에 쓰는 기간(어제부터 N일)
    const topN = Math.max(1, Math.min(10, Number(url.searchParams.get('top') || 6)));   // 보낼 개수
    const sample = url.searchParams.get('sample') === '1';

    // 1) 후보 기사 수집
    const candidates = await loadCandidates(sample);
    if (!candidates.length) {
      return res.status(400).json({ ok: false, error: 'no candidates (set NEWS_SOURCE_URL or use ?sample=1)' });
    }

    // 2) 전 채널 좋아요(모든 사용자)로 가중치 학습
    const liked = await collectAllLikesDays(days); // 어제~N일 모음
    const weights = buildWeightsFromLikes(liked);
    // 가중치가 비어 있으면(아직 좋아요가 거의 없으면) 원래 순서 그대로 보냄
    const ranked = Object.keys(weights).length ? scoreArticles(candidates, weights) : candidates.slice();

    // 3) 전송
    const day = dayStrKST(0); // 오늘 날짜 표기
    await tgSend(DT_CHANNEL_ID, `🗞️ DT 아침 뉴스 (${day} KST)\n(최근 ${days}일 좋아요 기반 개인화 정렬)`);

    let sent = 1;
    for (const a of ranked.slice(0, topN)) {
      const title = a.title || '제목 없음';
      const urlLine = a.url ? `\n${a.url}` : '';
      await tgSend(DT_CHANNEL_ID, `📰 ${title}${urlLine}`);
      sent++;
    }

    return res.status(200).json({
      ok: true,
      day,
      candidates: candidates.length,
      likeCount: liked.length,
      sent,
      usedWeights: Object.keys(weights).length
    });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
