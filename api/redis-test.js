// api/redis-test.js
export const config = { runtime: 'nodejs' };

import { Redis } from '@upstash/redis';
const redis = Redis.fromEnv(); // 환경변수 자동 인식

export default async function handler(req, res) {
  try {
    const now = Date.now().toString();
    await redis.set('newsbot:test', now);
    const val = await redis.get('newsbot:test');
    return res.status(200).json({ ok: true, value: val });
  } catch (e) {
    return res.status(500).json({ ok: false, error: String(e) });
  }
}
