// Checks the public link's live AI: /api/status, then one real streamed draft per account.
// Usage: node scripts/check_public_ai.mjs [url] [account ...]   (defaults: account-intel-live, advent_international hggc)
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const base = (process.argv[2] || 'https://account-intel-live.vercel.app').replace(/\/$/, '');
const accounts = process.argv.length > 3 ? process.argv.slice(3) : ['advent_international', 'hggc'];
const d = JSON.parse(readFileSync(path.join(root, 'workspace/data.public.json'), 'utf8'));

const status = await (await fetch(base + '/api/status')).json();
console.log('status', JSON.stringify(status));
if (!status.configured) { console.log('FAIL: AI is not connected (DEEPSEEK_API_KEY missing, or not redeployed after adding it).'); process.exit(1); }

let failed = 0;
for (const id of accounts) {
  const a = d.accounts.find(x => x.id === id);
  const body = { account_id: a.id, as_of: d.asOf,
    evidence: d.sources.filter(s => s.accountId === a.id && a.sourceIds.includes(s.id)).map(({ id, text, date, kind }) => ({ id, text, date, kind })),
    context: { name: a.name, strategy: a.strategy, fundContext: a.fundContext, product: 'LP obligation tracking' } };
  const t0 = Date.now();
  const res = await fetch(base + '/api/draft', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const text = await res.text();
  const last = text.trim().split('\n\n').pop() || '';
  const ok = res.status === 200 && last.startsWith('event: done');
  if (!ok) failed++;
  console.log(`${id}: ${ok ? 'PASS' : 'FAIL'} ${((Date.now() - t0) / 1000).toFixed(1)}s http ${res.status} ${ok ? '' : last.slice(0, 200)}`);
}
process.exit(failed ? 1 : 0);
