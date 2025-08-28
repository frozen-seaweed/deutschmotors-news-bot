// api/debug-report.js — send a one-line test to CHAT_ID_REPORT
import { sendMessage } from './common/telegram.js';

export default async function handler(req, res) {
  try {
    const url = new URL(req.url, 'http://localhost');
    const key = url.searchParams.get('key');
    if (key !== process.env.API_KEY) {
      return res.status(403).json({ error: 'forbidden' });
    }
    const chatId = process.env.CHAT_ID_REPORT;
    const r = await sendMessage(chatId, `DEBUG ping ${new Date().toISOString()}`, { disablePreview: true });
    return res.status(200).json({ ok: true, chatId, telegram: r });
  } catch (e) {
    return res.status(500).json({ ok: false, chatId: process.env.CHAT_ID_REPORT, error: String(e?.message || e) });
  }
}
