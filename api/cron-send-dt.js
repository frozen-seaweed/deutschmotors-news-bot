// api/cron-send-dt.js
// 아침 뉴스 발송(완성본): NewsAPI(키), DailyCar, Global-Autonews → 합치고 중복 제거 → 좋아요 기반 점수 정렬 → DT 채널 전송
export const config = { runtime: 'nodejs' };

import * as cheerio from 'cheerio';
import iconv from 'iconv-lite';
import { getAllLikesByDay } from '../lib/store.js';
import { buildWeightsFromLikes, scoreArticles } from '../lib/recommend.js';

const BOT = process.env.TELEGRAM_BOT_TOKEN;
const DT_CHANNEL_ID = process.env.DT_CHANNEL_ID;      // ex) -1002654852233
const NEWS_API_KEY = process.env.NEWS_API_KEY;        // ex) d753d2e4619c46888b7243b90c9962ea

function dayStrKST(offset = 0) {
  const t = Date.now() + 9 * 60 * 60 * 1000 - offset * 24 * 60 * 60 * 1000;
  return new Date(t).toISOString().slice(0, 10);
}
async function collectAllLikesDays(days) {
  const liked = [];
  for (let i = 1; i <= days; i++) { // 어제부터 N일까지
    const d = dayStrKST(i);
    const items = await getAllLikesByDay(d);
    liked.push(...items);
  }
  return liked;
}

// ---- 공통 유틸
function tidy(s = "") { return (s || "").replace(/\s+/g, " ").trim(); }
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

// ---- fetch + 인코딩(스크랩용)
async function fetchBuffer(url) {
  const r = await fetch(url, { headers: { 'User-Agent': 'news-bot/1.0' } });
  const buf = Buffer.from(await r.arrayBuffer());
  const ctype = (r.headers.get('content-type') || '').toLowerCase();
  let enc = (ctype.match(/charset=([^;]+)/i)?.[1] || '').toLowerCase() || 'utf-8';
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

// ---- NewsAPI(키 기반)
async function loadFromNewsAPI() {
  if (!NEWS_API_KEY) return [];
  const endpoint = 'https://newsapi.org/v2/everything';
  const q = encodeURIComponent('(자동차 OR 전기차 OR 배터리 OR 자율주행 OR 현대차 OR 기아 OR 제네시스 OR 테슬라 OR 모빌리티)');
  const url = `${endpoint}?q=${q}&language=ko&sortBy=publishedAt&pageSize=50&apiKey=${NEWS_API_KEY}`;
  try {
    const r = await fetch(url, { headers: { 'Accept': 'application/json' } });
    const j = await r.json();
    const arts = Array.isArray(j?.articles) ? j.articles : [];
    return arts.map(a => normalize({ title: a.title, summary: a.description, url: a.url }));
  } catch { return []; }
}

// ---- DailyCar
async function scrapeDailyCar() {
  try {
    const html = await fetchBuffer('https://www.dailycar.co.kr/');
    const $ = cheerio.load(html);
    const out = [];
    $('a[href]').each((_, a) => {
      const $a = $(a);
      const title = tidy($a.attr('title') || $a.text());
      let href = $a.attr('href') || '';
      if (!title || title.length < 10) return;
      if (!/^https?:/i.test(href)) { try { href = new URL(href, 'https://www.dailycar.co.kr/').href; } catch {} }
      if (/\/Notice|\/Event|login|member|#/.test(href)) return;
      if (href.includes('dailycar.co.kr')) out.push({ title, summary: '', url: href });
    });
    return dedupe(out).slice(0, 40);
  } catch { return []; }
}

// ---- Global-Autonews
async function scrapeGlobalAutonews() {
  try {
    const html = await fetchBuffer('http://www.global-autonews.com/home.php');
    const $ = cheerio.load(html);
    const out = [];
    const candidates = ['a[href*="/view.php"]','a[href*="home.php"]','a[href]'];
    $(candidates.join(',')).each((_, a) => {
      const $a = $(a);
      const title = tidy($a.attr('title') || $a.text());
      let href = $a.attr('href') || '';
      if (!title || title.length < 10) return;
      if (!/^https?:/i.test(href)) { try { href = new URL(href, 'http://www.global-autonews.com/').href; } catch {} }
      if (!href.includes('global-autonews.com')) return;
      out.push({ title, summary: '', url: href });
    });
    return dedupe(out).slice(0, 40);
  } catch { return []; }
}

// ---- 후보 합치기
async function loadCandidates() {
  const [newsapi, dc, ga] = await Promise.all([loadFromNewsAPI(), scrapeDailyCar(), scrapeGlobalAutonews()]);
  return dedupe([...newsapi, ...dc, ...ga]).slice(0, 100);
}

export default async function handler(req, res) {
  try {
    if (!BOT || !DT_CHANNEL_ID) {
      return res.status(500).json({ ok: false, error: 'Missing TELEGRAM_BOT_TOKEN or DT_CHANNEL_ID' });
    }

    const url = new URL(req.url, `http://${req.headers.host}`);
    const days = Math.max(1, Math.min(60, Number(url.searchParams.get('days') || 30)));
    const topN = Math.max(1, Math.min(20, Number(url.searchParams.get('top') || 8)));

    // 1) 후보 수집(기존 뉴스 API + 2개 스크랩)
    const candidates = await loadCandidates();
    if (!candidates.length) return res.status(400).json({ ok: false, error: 'no candidates' });

    // 2) 최근 N일 좋아요로 가중치 학습(머신러닝)
    const liked = await collectAllLikesDays(days);
    const weights = buildWeightsFromLikes(liked);
    const ranked = Object.keys(weights).length ? scoreArticles(candidates, weights) : candidates;

    // 3) 전송
    const day = dayStrKST(0);
    await tgSend(DT_CHANNEL_ID, `🗞️ DT 아침 뉴스 (${day} KST)\n(최근 ${days}일 좋아요 기반 정렬 / ${candidates.length}건 중 상위 ${topN})`);
    let sent = 1;
    for (const a of ranked.slice(0, topN)) {
      const title = a.title || '제목 없음';
      const link = a.url ? `\n${a.url}` : '';
      await tgSend(DT_CHANNEL_ID, `📰 ${title}${link}`);
      sent++;
    }

    return res.status(200).json({ ok: true, day, candidates: candidates.length, likeCount: liked.length, sent, usedWeights: Object.keys(weights).length, target: DT_CHANNEL_ID });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
