// lib/store.js
import { Redis } from '@upstash/redis';
const redis = Redis.fromEnv();

function safeParse(v) {
  if (v == null) return null;
  if (typeof v === 'string') {
    try { return JSON.parse(v); } catch { return { _raw: v }; }
  }
  return v;
}

/** 좋아요 기사 1건 저장 (보관기간 기본 14일) */
export async function saveLike({ userId, dayKST, article }) {
  const key = `likes:${userId}:${dayKST}`; // 예: likes:12345:2025-08-25
  await redis.lpush(key, JSON.stringify(article));
  await redis.expire(key, 60 * 60 * 24 * 14); // 14일
}

/** 특정 사용자/날짜(KST)의 좋아요 목록 */
export async function getLikesByDay({ userId, dayKST }) {
  const key = `likes:${userId}:${dayKST}`;
  const items = await redis.lrange(key, 0, -1);
  return items.map(safeParse).filter(Boolean);
}

/** 최근 학습 프로필 저장/조회 */
export async function saveUserProfile(userId, weights) {
  await redis.set(`kw:${userId}`, JSON.stringify(weights));
}
export async function getUserProfile(userId) {
  const raw = await redis.get(`kw:${userId}`);
  if (!raw) return {};
  return typeof raw === 'string' ? (JSON.parse(raw) || {}) : raw;
}

/** 패턴으로 모든 키 스캔 */
async function scanAllKeys(pattern, count = 200) {
  let cursor = 0;
  const keys = [];
  // Upstash는 cursor가 숫자 또는 문자열로 올 수 있음
  while (true) {
    const r = await redis.scan(cursor, { match: pattern, count });
    if (Array.isArray(r) && r.length === 2) {
      // 호환 처리: [cursor, keys] 형태인 경우
      cursor = typeof r[0] === 'string' ? parseInt(r[0], 10) : r[0];
      keys.push(...(r[1] || []));
    } else {
      cursor = typeof r.cursor === 'string' ? parseInt(r.cursor, 10) : r.cursor;
      keys.push(...(r.keys || []));
    }
    if (!cursor) break;
  }
  return keys;
}

/** 특정 날짜(KST)의 "모든 사용자" 좋아요를 합쳐서 반환 */
export async function getAllLikesByDay(dayKST) {
  const pattern = `likes:*:${dayKST}`;
  const keys = await scanAllKeys(pattern);
  const all = [];
  for (const k of keys) {
    const items = await redis.lrange(k, 0, -1);
    for (const it of items) {
      const obj = safeParse(it);
      if (obj) all.push(obj);
    }
  }
  return all;
}
