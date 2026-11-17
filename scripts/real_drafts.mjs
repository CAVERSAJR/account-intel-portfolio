// Real drafts for every account against a running build, checked by the same client validator the page uses.
// Usage: node scripts/real_drafts.mjs <base url> <engine.js> <rounds> [out.json]   (set IDS=advent,ta to limit accounts)
import { readFileSync, writeFileSync } from 'node:fs';
const [base0, enginePath, roundsArg, outPath] = process.argv.slice(2);
const base = base0.replace(/\/$/, ''); const rounds = Number(roundsArg || 1);
globalThis.window = globalThis; globalThis.localStorage = { getItem: () => null, setItem: () => {} };
(0, eval)(readFileSync(enginePath, 'utf8'));
const E = globalThis.AccountIntelEngine;
const ids = (process.env.IDS || 'advent,francisco,battery,audax,gi,summit,vista,thoma,gtcr,ta,hggc').split(',');
const SLOP = /\b(delve|leverag\w*|seamless\w*|unlock\w*|empower\w*|robust|streamlin\w*|game-chang\w*|cutting-edge|supercharg\w*|holistic|synerg\w*|pain points?|circle back|touch base|reach out|hope this (?:email|message|note) finds you|i hope you(?:'re| are) well|excited to|thrilled|revolutioni[sz]\w*|transform\w*|best-in-class|world-class|tailored|bespoke|navigate the|in today's|landscape|ensure|guarantee\w*)\b/gi;
const results = [];
for (let round = 1; round <= rounds; round++) for (const id of ids) {
  const champ = E.contacts(id)[0]; const req = E.request(id, 'LP obligation tracking', champ.id);
  const t0 = Date.now(); let row = { id, round };
  try {
    const res = await fetch(base + '/api/draft', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(req.body) });
    const text = await res.text(); const frames = text.trim().split('\n\n'); const last = frames.pop() || '';
    row.seconds = +((Date.now() - t0) / 1000).toFixed(1); row.http = res.status;
    if (res.status !== 200 || !last.startsWith('event: done')) { row.ok = false; row.error = last.slice(0, 240); results.push(row); console.log(JSON.stringify(row)); continue; }
    const done = JSON.parse(last.split('\n').find(l => l.startsWith('data:')).slice(5));
    row.retried = frames.some(f => f.startsWith('event: retry') || /"retry"/.test(f));
    const rawText = JSON.stringify([done.fields, done.questions, done.actions, done.email]);
    row.rawInvestorTerm = (rawText.match(/investor[- ]obligation|investor-specific/gi) || []).length;
    const plan = E.validate(id, done);
    const shown = JSON.stringify([plan.fields.filter(f => f.id !== 'snapshot' && f.id !== 'demo_motion'), plan.questions, plan.actions, plan.email]);
    row.ok = true;
    row.shownInvestorTerm = (shown.match(/investor[- ]obligation|investor-specific/gi) || []).length;
    row.recipientOk = !!plan.email && plan.email.contactId === champ.id; row.to = champ.name; row.dash = (shown.match(/[20142013]/g) || []).length; row.lpTerm = (shown.match(/\bLP[- ]obligation|\bLP-specific|\bLPs?\b/g) || []).length;
    row.slop = [...new Set((shown.match(SLOP) || []).map(x => x.toLowerCase()))];
    const model = plan.fields.filter(f => f.id !== 'snapshot' && f.id !== 'demo_motion');
    row.sourced = model.filter(f => f.basis === 'hypothesis' && f.sourceIds.length).length + '/' + model.filter(f => f.basis === 'hypothesis').length;
    row.unknowns = model.filter(f => f.basis === 'unknown').length;
    row.email = plan.email ? { to: plan.email.contactId, subject: plan.email.subject, words: plan.email.body.split(/\s+/).length, body: plan.email.body } : null;
    row.fields = Object.fromEntries(model.map(f => [f.id, f.value]));
    row.questions = plan.questions;
  } catch (e) { row.ok = false; row.error = String(e && e.message || e).slice(0, 240); row.seconds = +((Date.now() - t0) / 1000).toFixed(1); }
  results.push(row);
  console.log(`${id.padEnd(10)} r${round} ${row.ok ? 'PASS' : 'FAIL'} ${row.seconds}s sourced=${row.sourced || '-'} rawInvestor=${row.rawInvestorTerm ?? '-'} shownInvestor=${row.shownInvestorTerm ?? '-'} slop=${JSON.stringify(row.slop || [])} to=${row.to} recipientOk=${row.recipientOk} dash=${row.dash} ${row.ok ? '' : row.error}`);
}
const pass = results.filter(r => r.ok).length;
console.log(`TOTAL ${pass}/${results.length} passed; median ${results.filter(r => r.ok).map(r => r.seconds).sort((a, b) => a - b)[Math.floor(pass / 2)]}s`);
if (outPath) writeFileSync(outPath, JSON.stringify(results, null, 1));
