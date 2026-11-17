// Hosted-function checks without a model call: request and response validation in app/api/_lib/guard.js.
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, resolve } from 'node:path';
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const g = await import(pathToFileURL(ROOT + '/app/api/_lib/guard.js').href);
const data = (await import(pathToFileURL(ROOT + '/app/api/_lib/data.js').href)).default;
let pass = 0, total = 0;
const check = (label, ok, detail = '') => { total++; if (ok) pass++; console.log((ok ? 'PASS' : 'FAIL') + ' · ' + label + (ok ? '' : ' · ' + detail)); };
const throws = fn => { try { fn(); return null; } catch (e) { return e.message || String(e); } };

const a = data.accounts.find(x => x.id === 'battery_ventures');
const evidence = data.sources.filter(s => s.accountId === a.id && a.sourceIds.includes(s.id)).map(({ id, text, date, kind }) => ({ id, text, date, kind }));
const gc = evidence.find(e => /Lizette/.test(e.text)).id, cfo = evidence.find(e => /Schiavo/.test(e.text)).id;
const request = (extra = {}) => ({ account_id: a.id, as_of: data.asOf, evidence, context: { name: a.name, strategy: a.strategy, fundContext: a.fundContext, product: g.PRODUCT, ...extra } });
const plan = (email = {}) => ({ account_id: a.id,
  fields: ['goals', 'pain', 'people', 'strategy', 'next_action'].map(id => ({ id, label: id, basis: 'hypothesis', source_ids: [a.id + '-event'], value: 'Hypothesis: ask how the Fund XV side letter obligations are tracked.' })),
  questions: ['How are side letter obligations tracked today?'], actions: ['Email the General Counsel.'],
  email: { contact_id: gc, subject: 'Side letters after Fund XV', body: 'Hi Lizette, I saw Battery announced Battery Ventures XV in February. How are the new side letter obligations tracked today?', ...email } });

check('Battery Ventures is in the hosted dataset with 11 public sources', evidence.length === 11 && evidence.every(e => e.kind === 'public'));
check('Product context is the LP wording', g.PRODUCT === 'LP obligation tracking', g.PRODUCT);
check('Request without a recipient is accepted', throws(() => g.validateRequest(request())) === null);
check('Request with the chosen contact as recipient is accepted', throws(() => g.validateRequest(request({ recipient: gc }))) === null);
check('Recipient that is not a contact profile is rejected', /recipient/.test(throws(() => g.validateRequest(request({ recipient: a.id + '-event' }))) || ''));
check('Recipient from another account is rejected', /recipient/.test(throws(() => g.validateRequest(request({ recipient: 'CT-2f153a16442e-profile' }))) || ''));
check('Old product string is rejected', throws(() => g.validateRequest({ ...request(), context: { ...request().context, product: 'investor obligation management' } })) !== null);
check('A plain, sourced plan passes', throws(() => g.validateModelResponse(plan(), request({ recipient: gc }))) === null, throws(() => g.validateModelResponse(plan(), request({ recipient: gc }))));
check('Email to a different contact than the one chosen is rejected', throws(() => g.validateModelResponse(plan({ contact_id: cfo, body: 'Hi Chris, how are side letter obligations tracked today?' }), request({ recipient: gc }))) !== null);
check('Without a chosen recipient, any sourced contact is allowed', throws(() => g.validateModelResponse(plan({ contact_id: cfo, body: 'Hi Chris, how are side letter obligations tracked today?' }), request())) === null);
for (const phrase of ['I imagine tracking gets harder each fund.', 'I wanted to reach out directly.', 'A seamless, robust way to track them.', 'Could a bespoke report help?', 'I am curious how you track them.']) {
  check('Filler rejected: ' + phrase, throws(() => g.validateModelResponse(plan({ body: 'Hi Lizette, ' + phrase }), request())) !== null);
}
check('The Nov 15 HGGC phrase is still rejected', throws(() => g.validateModelResponse(plan({ body: 'Hi Lizette, can you describe the illustrative service escalation in this fictional scenario?' }), request())) !== null);
check('"Schedule a demo" still passes', throws(() => g.validateModelResponse({ ...plan(), actions: ['Schedule a demo with the General Counsel.'] }, request())) === null);
check('"Leveraged buyout" is not treated as filler', throws(() => g.validateModelResponse({ ...plan(), questions: ['How does the leveraged buyout fund track side letter obligations?'] }, request())) === null);
console.log(`TOTAL ${pass}/${total}`);
process.exit(pass === total ? 0 : 1);
