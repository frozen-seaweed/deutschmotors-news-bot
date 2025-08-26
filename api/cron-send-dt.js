// api/cron-send-dt.js
// NewsAPI + DailyCar + Global-Autonews → 합치기/중복제거 → 좋아요 기반 정렬 → DT 채널 전송 (UTF-8 안전 버전)
export const config = { runtime: "nodejs" };

import * as cheerio from "cheerio";
import { getAllLikesByDay } from "../lib/store.js";
import { buildWeightsFromLikes, scoreArticles } from "../lib/recommend.js";

const BOT = process.env.TELEGRAM_BOT_TOKEN;
const DT_CHANNEL_ID = process.env.DT_CHANNEL_ID;      // -1002654852233
const NEWS_API_KEY  = process.env.NEWS_API_KEY;       // d753d2e4619c46888b7243b90c9962ea

// 공통
const tidy = (s="") => s.replace(/\s+/g, " ").trim();
const sanitize = (s="") =>
  String(s)
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "")
    .replace(/[\uD800-\uDFFF]/g, "")
    .trim();
const norm = (x={}) => ({ title: x.title||x.headline||"", summary: x.summary||x.description||"", url: x.url||x.link||"" });
const dedupe = (list=[]) => {
  const map=new Map();
  for (const raw of list) {
    const a=norm(raw); const key=(a.url||a.title).toLowerCase().trim();
    if (!key) continue; if (!map.has(key)) map.set(key,a);
  } return [...map.values()];
};
const kstDay = (offset=0) => {
  const t=Date.now()+9*3600*1000-offset*24*3600*1000;
  return new Date(t).toISOString().slice(0,10);
};
async function collectLikes(days){
  const liked=[];
  for(let i=1;i<=days;i++){ const d=kstDay(i); const items=await getAllLikesByDay(d); liked.push(...items); }
  return liked;
}
async function tgSend(chatId, text){
  const api=`https://api.telegram.org/bot${BOT}/sendMessage`;
  const body={ chat_id: chatId, text: sanitize(text), parse_mode:"HTML", disable_web_page_preview:false };
  const r=await fetch(api,{ method:"POST", headers:{ "Content-Type":"application/json; charset=utf-8" }, body: JSON.stringify(body) });
  const j=await r.json(); if(!j.ok) throw new Error(j.description||"telegram error"); return j;
}

// 인코딩 자동 처리 fetch(동적 iconv 사용)
async function fetchTextSmart(url){
  const r=await fetch(url,{ headers:{ "User-Agent":"news-bot/1.0" } });
  const buf=Buffer.from(await r.arrayBuffer());
  let text=buf.toString("utf-8");
  try{
    const ctype=(r.headers.get("content-type")||"").toLowerCase();
    const headerCharset=(ctype.match(/charset=([^;]+)/i)||[])[1];
    const metaProbe=(text.match(/charset=["']?([\w-]+)/i)||[])[1];
    const enc=(headerCharset||metaProbe||"utf-8").toLowerCase();
    if(enc && enc!=="utf-8"){
      const { default: iconv } = await import("iconv-lite");
      if(iconv?.decode) text=iconv.decode(buf, enc);
    }
  }catch{}
  return text;
}

// 소스 1: NewsAPI
async function loadFromNewsAPI(){
  if(!NEWS_API_KEY) return [];
  try{
    const endpoint="https://newsapi.org/v2/everything";
    const q=encodeURIComponent("(자동차 OR 전기차 OR 배터리 OR 자율주행 OR 현대차 OR 기아 OR 제네시스 OR 테슬라 OR 모빌리티)");
    const url=`${endpoint}?q=${q}&language=ko&sortBy=publishedAt&pageSize=50&apiKey=${NEWS_API_KEY}`;
    const r=await fetch(url,{ headers:{ Accept:"application/json" }});
    const j=await r.json().catch(()=>({}));
    const arr=Array.isArray(j?.articles)?j.articles:[];
    return arr.map(a=>norm({ title:a.title, summary:a.description, url:a.url }));
  }catch{ return []; }
}

// 소스 2: DailyCar
async function scrapeDailyCar(){
  try{
    const html=await fetchTextSmart("https://www.dailycar.co.kr/");
    const $=cheerio.load(html); const out=[];
    $("a[href]").each((_,el)=>{
      const $a=$(el); const title=tidy($a.attr("title")||$a.text()); let href=$a.attr("href")||"";
      if(!title||title.length<10) return;
      if(!/^https?:/i.test(href)){ try{ href=new URL(href,"https://www.dailycar.co.kr/").href; }catch{} }
      if(/\/Notice|\/Event|login|member|#/.test(href)) return;
      if(href.includes("dailycar.co.kr")) out.push({ title, summary:"", url: href });
    });
    return dedupe(out).slice(0,40);
  }catch{ return []; }
}

// 소스 3: Global-Autonews
async function scrapeGlobalAutonews(){
  try{
    const html=await fetchTextSmart("http://www.global-autonews.com/home.php");
    const $=cheerio.load(html); const out=[]; 
    const cand=['a[href*="/view.php"]','a[href*="home.php"]',"a[href]"];
    $(cand.join(",")).each((_,el)=>{
      const $a=$(el); const title=tidy($a.attr("title")||$a.text()); let href=$a.attr("href")||"";
      if(!title||title.length<10) return;
      if(!/^https?:/i.test(href)){ try{ href=new URL(href,"http://www.global-autonews.com/").href; }catch{} }
      if(!href.includes("global-autonews.com")) return;
      out.push({ title, summary:"", url: href });
    });
    return dedupe(out).slice(0,40);
  }catch{ return []; }
}

// 후보 합치기
async function loadCandidates(){
  const [newsapi, dc, ga] = await Promise.all([loadFromNewsAPI(), scrapeDailyCar(), scrapeGlobalAutonews()]);
  return dedupe([...newsapi, ...dc, ...ga]).slice(0,100);
}

export default async function handler(req,res){
  try{
    if(!BOT) return res.status(500).json({ ok:false, error:"Missing TELEGRAM_BOT_TOKEN" });
    const url=new URL(req.url, `http://${req.headers.host}`);
    const chatId=url.searchParams.get("chatId")||DT_CHANNEL_ID;
    if(!chatId) return res.status(500).json({ ok:false, error:"Missing DT_CHANNEL_ID" });

    const days=Math.max(1,Math.min(60, Number(url.searchParams.get("days")||30)));
    const topN=Math.max(1,Math.min(20, Number(url.searchParams.get("top")||8)));

    const candidates=await loadCandidates();
    if(!candidates.length) return res.status(400).json({ ok:false, error:"no candidates" });

    const liked=await collectLikes(days);
    const weights=buildWeightsFromLikes(liked);
    const ranked=Object.keys(weights).length?scoreArticles(candidates,weights):candidates;

    const day=kstDay(0);
    try{ await tgSend(chatId, `🗞️ DT 아침 뉴스 (${day} KST)\n(최근 ${days}일 좋아요 기반 정렬 / ${candidates.length}건 중 상위 ${topN})`);}catch{}
    let sent=1, fail=0;
    for(const a of ranked.slice(0,topN)){
      const title=a.title||"제목 없음"; const link=a.url?`\n${a.url}`:"";
      try{ await tgSend(chatId, `📰 ${title}${link}`); sent++; }catch{ fail++; }
    }
    return res.status(200).json({ ok:true, day, candidates:candidates.length, likeCount:liked.length, sent, fail, usedWeights:Object.keys(weights).length, target:chatId });
  }catch(e){
    return res.status(500).json({ ok:false, error:String(e) });
  }
}
