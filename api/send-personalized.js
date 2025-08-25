// api/send-personalized.js
export const config = { runtime: 'nodejs' };

import { getUserProfile, getLikesByDay, saveUserProfile } from '../lib/store.js';
import { buildWeightsFromLikes, scoreArticles } from '../lib/recommend.js';

const BOT = process.env.TELEGRAM_BOT_TOKEN;

function dayStrKST(offset = 0) {
  const t = Date.now() + 9 * 60 * 60 * 1000 - offset * 24 * 60 * 60 * 1000;
  return new Date(t).toISOString().slice(0, 10);
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

async function tgSend(chatId, text, url = null) {
  const api = `https://api.telegram.org/bot${BOT}/sendMessage`;
  const body = {
    chat_id: chatId,
    text: url ? `${text}\n${url}` : text,
    parse_mode: 'HTML',
    disable_web_page_preview: false,
  };
  const r = await fetch(api, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!j.ok) throw new Error(`Telegram send failed: ${JSON.stringify(j)}`);
  return j;
}

export default async function handler(req, res) {
  try {
    if (!BOT) return res.status(500).json({ ok: false, error: 'Missing TELEGRAM_BOT_TOKEN' });

    const url = new URL(req.url, `http://${req.headers.host}`);
    const userId = url.searchParams.get('userId') || 'test';
    const chatId = url.searchParams.get('chatId'); // 필수
    const topN = Math.max(1, Math.min(10, Number(url.searchParams.get('top') || 4)));
    const days = Math.max(1, Math.min(60, Number(url.searchParams.get('days') || 30)));
    const sample = url.searchParams.get('sample') === '1';

    if (!chatId) return res.status(400).json({ ok: false, error: 'chatId required' });

    // 1) 후보 기사: 우선 샘플로 테스트
    let candidates = [];
    if (sample) {
      candidates = [
        { title: '전기차 판매 급증', summary: '배터리 원가 하락과 충전 인프라 확대', url: 'https://example.com/ev-sales' },
        { title: '국내 증시 상승세', summary: '은행주 강세로 코스피 상승', url: 'https://example.com/kospi' },
        { title: 'AI 반도체 수요 폭발', summary: '고성능 칩 공급난 지속', url: 'https://example.com/ai-chip' },
        { title: '신형 SUV 출시', summary: '가솔린 모델 라인업 강화', url: 'https://example.com/new-suv' }
      ];
    } else {
      // 나중에 실제 수집 결과(뉴스 API+스크래핑)를 여기에 넣을 예정
      return res.status(400).json({ ok: false, error: 'no candidates; use ?sample=1 for now' });
    }

    // 2) 사용자 프로필(가중치)
    let weights = await getUserProfile(userId);
    let profileSource = 'saved';
    if (!weights || Object.keys(weights).length === 0) {
      const liked = await collectLikesDays(userId, days);
      if (liked.length === 0) {
        return res.status(200).json({ ok: true, note: 'no likes yet; press like or seed first', sent: 0 });
      }
      weights = buildWeightsFromLikes(liked);
      await saveUserProfile(userId, weights);
      profileSource = 'built_from_likes';
    }

    // 3) 점수화 후 상위 N개 발송
    const ranked = scoreArticles(candidates, weights).slice(0, topN);

    // 안내 메시지 1건
    await tgSend(chatId, `개인화 추천 테스트 (userId=${userId}, source=${profileSource})`);

    let sent = 0;
    for (const a of ranked) {
      const title = a.title || '제목 없음';
      const urlStr = a.url || '';
      await tgSend(chatId, `📰 ${title}`, urlStr);
      sent++;
    }

    return res.status(200).json({
      ok: true,
      userId,
      profileSource,
      candidates: candidates.length,
      sent,
      topPreview: ranked
    });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
