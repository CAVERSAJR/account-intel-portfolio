// GET /api/status — tells the app whether live AI is connected on this site. Never returns the key.
import { MODEL } from './_lib/guard.js';

export function GET() {
  const configured = Boolean((process.env.DEEPSEEK_API_KEY || '').trim());
  return new Response(JSON.stringify({ configured, provider: 'deepseek', model: MODEL }),
    { headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
}
