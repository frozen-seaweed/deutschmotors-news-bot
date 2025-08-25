// lib/store.js
import { Redis } from '@upstash/redis';
const redis = Redis.fromEnv();

/** 좋아요 기사 1건 저장 (보관기간 기본 14일) */
export async function saveLike({ userId, dayKST, article }) {
  const key = `likes:${userId}:${dayKST}`; // 예: likes:12345:2025-08-25
  await redis.lpush(key, JSON.stringify(article));
  // 14일 후 만료 (필요 시 조정 가능)
  await redis.expire(key, 60 * 60 * 24 * 14);
}

/** 특정 날짜(KST) 좋아요 기사 목록 조회 */
export async function getLikesByDay({ userId, dayKST }) {
  const key = `likes:${userId}:${dayKST}`;
  const items = await redis.lrange(key, 0, -1);
  return items.map(JSON.parse);
}

/** 사용자 키워드 가중치 저장/조회 (개인화 프로필) */
export async function saveUserProfile(userId, weights) {
  await redis.set(`kw:${userId}`, JSON.stringify(weights));
}

export async function getUserProfile(userId) {
  const raw = await redis.get(`kw:${userId}`);
  return raw ? JSON.parse(raw) : {};
}
