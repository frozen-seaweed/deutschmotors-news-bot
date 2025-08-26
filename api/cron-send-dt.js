// api/cron-send-dt.js
// 아침 뉴스 발송: "기존 뉴스 API(JSON)" + "DailyCar/Global-Autonews 스크랩" → 합치고 중복 제거 → 좋아요 기반(ML) 점수 정렬 → DT 채널 전송
export const config = { runtime: 'nodejs' };

import * as cheerio from 'cheerio';
import iconv from 'iconv-lite';
import { getAllLikesByDay } from '../lib/store.js';
import { buildWeightsFromLikes, scoreArticles } from '../lib/recommend.js';

const BOT = process.env.TELEGRAM_BOT_TOKEN;
const DT_CHANNEL_ID_ENV = process.env.DT_CHANNEL_ID; // 없으면 ?chatId= 로 대체 가능

// ↓↓↓ 네 "기존 뉴스 API URL" 이 있으면 여기 따옴표 안에 넣어두면 됨(몰라도 됨).
const EXISTING_API_URL = ""; // 예: "https://your-api.example.com/news?limit=50"

function dayStrKST(offset = 0) {
  const t = Date.now() + 9 * 60 * 60 * 1000 - offset * 24 * 60 * 60 * 1000;
  return new Date(t).toISOString().slice(0, 10);
}
async function collectAllLikesDays(days) {
  const liked = [];
  for (let i = 1; i <= days; i++) {
    const d = dayStrKST(i);
    const items = await getAllLikesByDay(d);
    liked.push(...items);
  }
  return liked;
}

// ---------- 공통 유틸 ----------
function tidy(s = "") { return s.replace(/\s+/g, " ").trim(); }
function normalize(x = {}) {
  return { title: x.title || x.headline || "", summary: x.summary || x.description || "", url: x.url || x.link || "" };
}
function dedupe(arr) {
  const map = new Map();
  for (const raw of arr) {
    const a = normalize(raw);
    const key = (a.url || a.title).toLowerCase().trim();
    if (!key) continue;
    if (!map.has(key)) map.set(key, a);
  }
  return [...map.values()];
}
async function tgSend(chatId, text) {
  const api = `https://api.telegram.org/bot${BOT}/sendMessage`;
  const body = { chat_id: chatId, text, parse_mode: 'HTML', disable_web_page_preview: false };
  const r = await fetch(api, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!j.ok) throw new Error(`Telegram send failed: ${JSON.stringify(j)}`);
  return j;
}

// ---------- fetch + 인코딩 ----------
async function fetchBuffer(url) {
  const r = await fetch(url, { headers: { 'User-Agent': 'news-bot/1.0' } });
  const buf = Buffer.from(await r.arrayBuffer());
  const ctype = (r.headers.get('content-type') || '').toLowerCase();
  // content-type에 charset이 있으면 우선 사용
  let enc = (ctype.match(/charset=([^;]+)/i)?.[1] || '').toLowerCase() || 'utf-8';
  // 없으면 본문에서 meta charset 추정
  let text = iconv.decode(buf, enc);
  if (!/charset=/i.test(ctype)) {
    const m = (text.match(/<meta[^>]+charset=["']?([\w-]+)/i) || [])[1]
          || (text.match(/<meta[^>]+content=["'][^"']*charset=([\w-]+)/i) || [])[1];
    if (m && m.toLowerCase() !== enc) {
      enc = m.toLowerCase();
      text = iconv.decode(buf, enc);
    }
  }
  return text;
}

// ---------- JSON 기존 API ----------
async function loadFromExistingApi(url) {
  try {
    const r = await fetch(url, { headers: { Accept: 'application/json' } });
    const j = await r.json();
    const items = Array.isArray(j) ? j : (Array.isArray(j?.items) ? j.items : []);
    return items.map(normalize);
  } catch { return []; }
}

// ---------- DailyCar 스크랩 ----------
async function scrapeDailyCar() {
  try {
    const html = await fetchBuffer('https://www.dailycar.co.kr/');
    const $ = cheerio.load(html);
    const out = [];
    // 메인/리스트에서 a 태그 추출 (필터: 길이/중복)
    $('a[href]').each((_, a) => {
      const $a = $(a);
      const title = tidy($a.attr('title') || $a.text());
      let href = $a.attr('href') || '';
      if (!title || title.length < 10) return;
      if (!/^https?:/i.test(href)) {
        try { href = new URL(href, 'https://www.dailycar.co.kr/').href; } catch {}
      }
      if (/\/Notice|\/Event|login|member|#/.test(href)) return;
      if (href.includes('dailycar.co.kr')) out.push({ title, summary: '', url: href });
    });
    return dedupe(out).slice(0, 40);
  } catch { return []; }
}

// ---------- Global-Autonews 스크랩 ----------
async function scrapeGlobalAutonews() {
  try {
    const html = await fetchBuffer('http://www.global-autonews.com/home.php');
    const $ = cheerio.load(html);
    const out = [];
    // 리스트/기사 링크 후보
    const candidates = [
      'a[href*="/view.php"]',
      'a[href*="home.php"]',
      'a[href]'
    ];
    $(candidates.join(',')).each((_, a) => {
      const $a = $(a);
      const title = tidy($a.attr('title') || $a.text());
      let href = $a.attr('href') || '';
      if (!title || title.length < 10) return;
      if (!/^https?:/i.test(href)) {
        try { href = new URL(href, 'http://www.global-autonews.com/').href; } catch {}
      }
      if (!href.includes('global-autonews.com')) return;
      out.push({ title, summary: '', url: href });
    });
    return dedupe(out).slice(0, 40);
  } catch { return []; }
}

// ---------- 후보 수집(합치기) ----------
async function loadCandidates(req, useSample) {
  const u = new URL(req.url, 'http://x');
  const apiQ = u.searchParams.get('api'); // ?api=기존뉴스API 로 임시 덮어쓰기 가능
  const list = [];

  // 1) 기존 뉴스 API (있으면 사용)
  const apiUrl = apiQ || EXISTING_API_URL;
  if (apiUrl) {
    list.push(...await loadFromExistingApi(apiUrl));
  }

  // 2) 네가 요청한 2개 사이트 스크랩
  const [dc, ga] = await Promise.all([scrapeDailyCar(), scrapeGlobalAutonews()]);
  list.push(...dc, ...ga);

  // 3) 후보 없는데 샘플 요청이면 샘플 몇 개
  if (list.length === 0 && useSample) {
    list.push(
      { title: '전기차 판매 급증', summary: '배터리 원가 하락과 충전 인프라 확대', url: 'https://example.com/ev-sales' },
      { title: '국내 증시 상승세', summary: '은행주 강세로 코스피 상승', url: 'https://example.com/kospi' },
      { title: 'AI 반도체 수요 폭발', summary: '고성능 칩 공급난 지속', url: 'https://example.com/ai-chip' }
    );
  }

  return dedupe(list).slice(0, 80); // 최대 80개까지만 사용
}

export default async function handler(req, res) {
  try {
    if (!BOT) return res.status(500).json({ ok: false, error: 'Missing TELEGRAM_BOT_TOKEN' });

    const url = new URL(req.url, `http://${req.headers.host}`);
    const days = Math.max(1, Math.min(60, Number(url.searchParams.get('days') || 30)));
    const topN = Math.max(1, Math.min(20, Number(url.searchParams.get('top') || 6)));
    const sample = url.searchParams.get('sample') === '1';
    const chatIdParam = url.searchParams.get('chatId');
    const TARGET_CHAT_ID = chatIdParam || DT_CHANNEL_ID_ENV;

    if (!TARGET_CHAT_ID) {
      return res.status(500).json({ ok: false, error: 'Missing DT_CHANNEL_ID (env) or chatId (query param)' });
    }

    // 후보 수집(기존 API + 2개 스크랩)
    const candidates = await loadCandidates(req, sample);
    if (!candidates.length) {
      return res.status(400).json({ ok: false, error: 'no candidates (add EXISTING_API_URL in file or use ?api=)' });
    }

    // 좋아요 기반 가중치 만들고 정렬
    const liked = await collectAllLikesDays(days);
    const weights = buildWeightsFromLikes(liked);
    const ranked = Object.keys(weights).length ? scoreArticles(candidates, weights) : candidates;

    // 전송
    const day = dayStrKST(0);
    await tgSend(TARGET_CHAT_ID, `🗞️ DT 아침 뉴스 (${day} KST)\n(최근 ${days}일 좋아요 기반 정렬 / ${candidates.length}건 중 상위 ${topN})`);
    let sent = 1;
    for (const a of ranked.slice(0, topN)) {
      const title = a.title || '제목 없음';
      const link = a.url ? `\n${a.url}` : '';
      await tgSend(TARGET_CHAT_ID, `📰 ${title}${link}`);
      sent++;
    }

    return res.status(200).json({ ok: true, day, candidates: candidates.length, likeCount: liked.length, sent, usedWeights: Object.keys(weights).length, target: TARGET_CHAT_ID });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
