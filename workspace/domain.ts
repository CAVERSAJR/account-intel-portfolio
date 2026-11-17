import {
  DEFAULT_POLICY,
  type Account, type AccountScore, type Basis, type Brief, type BriefItem, type Dataset, type Plan,
  type PlanField, type Policy, type RankedAccount, type Review, type RunRecord,
  type ScoreDriver, type Source, type WorkspaceState,
} from './types';

const REQUIRED_FIELDS = ['goals', 'pain', 'people', 'strategy', 'next_action'];
const REVIEWS: Review[] = ['unreviewed', 'accepted', 'edited', 'rejected'];
const BASES: Basis[] = ['fact', 'hypothesis', 'unknown', 'scenario'];
// Seller-visible AI text must not carry demo labels or echo the server's routing instructions.
export const SELLER_LEAK = /\b(?:fictional|illustrative|simulated|scenarios?)\b|net_new|customer_hold|server_demo_policy|account_policy|\bdemo (?:hold|policy|lane|motion|data|workspace)\b|\bno (?:demo )?hold applies\b|\bhold does not apply\b|\bthe server\b|\binvestor commitments?\b|\bfund obligations?\b/i;
// Filler a seller would not write. The same list is in the local server and the hosted function.
// The buyer must never read that we watched their page views or email opens.
export const EMAIL_TRACKING = /\b(?:visit(?:ed|ors?)|viewed|looked at|page views?|clicked|downloaded|opened (?:my|our|the|your) (?:email|message|note|intro))\b|\b(?:your|the) (?:website|site) (?:activity|visits?)\b/i;
export const SELLER_FILLER = /\bI imagine\b|\bI hope\b|\bI(?:'m| am|\u2019m) curious\b|\breach(?:ing|ed)? out\b|\btouch(?:ing)? base\b|\bcircl(?:e|ing) back\b|\bdelv(?:e|es|ing)\b|\bseamless(?:ly)?\b|\bunlock(?:s|ed|ing)?\b|\bempower(?:s|ed|ing)?\b|\brobust\b|\bstreamlin(?:e|es|ed|ing)\b|\bgame-chang\w*|\bcutting-edge\b|\bsupercharg\w*|\bholistic\b|\bsynerg\w*|\bbespoke\b|\bbest-in-class\b|\bworld-class\b/i;
const wording = (...texts: string[]) => {
  for (const value of texts) {
    if (SELLER_LEAK.test(value)) throw new Error('AI text leaked demo or instruction wording.');
    if (SELLER_FILLER.test(value)) throw new Error('AI text used filler wording.');
  }
};
/** 'Hi Lizette, I saw...' becomes a greeting line, a blank line, then the message, so every draft is laid out the same way. */
export const greetingLine = (body: string) => {
  const match = /^((?:Hi|Hello|Dear)\s[^,\n]{1,40},)\s*([\s\S]+)$/.exec(body.trim());
  return match ? `${match[1]}\n\n${match[2].charAt(0).toUpperCase()}${match[2].slice(1)}` : body;
};

// Seller-visible AI text uses the buyer's standard term, LP (limited partner) obligations, and plain punctuation.
export const lpTerms = (text: string) => text
  .replace(/\s*\u2014\s*/g, ', ').replace(/\s+\u2013\s+/g, ', ')
  .replace(/\binvestor([- ])obligation/g, 'LP$1obligation').replace(/\bInvestor([- ])obligation/g, 'LP$1obligation')
  .replace(/\binvestor-specific\b/g, 'LP-specific').replace(/\bInvestor-specific\b/g, 'LP-specific');
const DAY = 86_400_000;
const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);
const record = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const string = (value: unknown, max = 24_000): value is string =>
  typeof value === 'string' && value.trim().length > 0 && value.length <= max;
const compare = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;
const unique = (values: string[]) => [...new Set(values)].sort(compare);
const now = () => new Date().toISOString();

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
/** 2026-07-23 -> Jul 23, 2026. Sellers never see a raw ISO date. */
function shortDate(value: string | null): string {
  if (!value) return "date unknown";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return match && MONTHS[Number(match[2]) - 1] ? `${MONTHS[Number(match[2]) - 1]} ${Number(match[3])}, ${match[1]}` : value;
}

function dateValue(value: string | null): number | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(value)) return null;
  const time = Date.parse(value.length === 10 ? `${value}T00:00:00Z` : value);
  if (!Number.isFinite(time) || new Date(time).toISOString().slice(0, 10) !== value.slice(0, 10)) return null;
  return time;
}

function evidence(account: Account, dataset: Dataset, state: WorkspaceState): Source[] {
  const ids = new Set([...account.sourceIds, ...account.eventIds]);
  return dataset.sources.filter(source => ids.has(source.id) && source.accountId === account.id &&
    state.sourceOverrides[source.id] !== false && source.text.trim().length > 0)
    .sort((a, b) => compare(a.id, b.id));
}

function publicEvidence(sources: Source[]): Source[] {
  return sources.filter(source => source.kind === 'public' && !!source.url && /^https?:\/\//i.test(source.url));
}

function contactLeads(account: Account, dataset: Dataset, state: WorkspaceState) {
  const activeProfileIds = new Set(publicEvidence(evidence(account, dataset, state)).map(source => source.id));
  const entryRole = (contact: Dataset['contacts'][number]) => {
    const role = `${contact.title} ${contact.function}`;
    if (/\blegal\b|\bcompliance\b|\bcounsel\b|\bGC\b|\bAGC\b|\bCCO\b|\bCLO\b/i.test(role)) return 0;
    if (/\boperations?\b|\boperating\b|\bCOO\b/i.test(role)) return 1;
    if (/\binvestor (?:relations?|services?)\b|\bIR\b|\bfundraising\b|\bcapital formation\b/i.test(role)) return 2;
    if (/\bfinanc(?:e|ial)\b|\bCFO\b|\bcontroller\b|\baccounting\b|\btreasur(?:y|er)\b/i.test(role)) return 3;
    return 4;
  };
  return dataset.contacts.filter(contact => contact.accountId === account.id && activeProfileIds.has(`${contact.id}-profile`))
    .sort((a, b) => entryRole(a) - entryRole(b) || compare(a.id, b.id));
}

function supportedFieldBases(fields: PlanField[]): boolean {
  return REQUIRED_FIELDS.every(id => fields.some(item => item.id === id && (item.basis === 'hypothesis' || item.basis === 'unknown'))) &&
    fields.every(item => (item.basis !== 'fact' || item.id === 'snapshot') &&
      (item.basis !== 'scenario' || item.id === 'demo_motion'));
}

function relevantEvent(source: Source): boolean {
  // Acquisition publicity alone is not a fund-obligation or fund-operating trigger.
  const text = `${source.title} ${source.text}`;
  const operating = /\b(?:LP|limited partner|side[- ]letter|MFN)\b[\s\S]{0,100}\b(?:obligations?|reporting|elections?|operations?|deadlines?)\b|\bfund[- ](?:operations|administration|reporting)\b/i.test(text);
  const fundraising = /\bfundrais(?:e|es|ed|ing)\b|\bfund[- ]?raise\b|\bfunds?\b[\s\S]{0,140}\brais(?:e|es|ed|ing)\b|\brais(?:e|es|ed|ing)\b[\s\S]{0,140}\bfunds?\b/i.test(text) ||
    // "Closed $21 billion across Fund VIII and Agility IV" is a capital close even without the word "fund".
    /\bclos(?:e|ed|es|ing)\s+(?:on\s+)?\$\s?[\d.,]+\s*(?:billion|million|bn|mm?)\b/i.test(text);
  if (operating || fundraising) return true;
  // "Fund VIII closed the acquisition" is a deal close, not a fund close.
  if (/\bacquisitions?\b|\bacquir(?:e|ed|es|ing)\b|\binvest(?:ment|ed|ing)\s+in\b|\btransaction\s+clos(?:e|ed|ing)\b|\bbuyout\s+of\b/i.test(text)) return false;
  return /\bfunds?\b[\s\S]{0,140}\b(?:clos(?:e|ed|es|ing)|launch(?:ed|es|ing)?)\b|\b(?:clos(?:e|ed|es|ing)|launch(?:ed|es|ing)?)\b[\s\S]{0,140}\bfunds?\b/i.test(text);
}

function currentEvents(account: Account, sources: Source[], asOf: string, policy: Policy): Source[] {
  const asOfTime = dateValue(asOf);
  if (asOfTime === null) return [];
  const ids = new Set(account.eventIds);
  return sources.filter(source => {
    const time = dateValue(source.date);
    if (!ids.has(source.id) || time === null || !relevantEvent(source)) return false;
    if (source.kind === 'public' && !publicEvidence([source]).length) return false;
    const days = (asOfTime - time) / DAY;
    return days >= 0 && days <= policy.warmDays;
  }).sort((a, b) => (dateValue(b.date)! - dateValue(a.date)!) || compare(a.id, b.id));
}

// Propensity score: four transparent drivers that add up to 10.
// Weights are starting hypotheses to calibrate against real outcomes, not a trained model.
export const SCORE_WEIGHTS = { timing: 4, fit: 3, reach: 2, evidence: 1 } as const;
export const SCORE_TIMING_WINDOW_DAYS = 365;
const STRATEGY_TERMS: [string, RegExp][] = [
  ['buyout / private equity', /\bbuyouts?\b|\bprivate equity\b/i],
  ['credit', /\bcredit\b|\bdebt\b|\blending\b/i],
  ['growth', /\bgrowth\b/i],
  ['real estate', /\breal estate\b/i],
  ['venture / early stage', /\bventure capital\b|\bearly[- ]stage\b/i],
  ['infrastructure', /\binfrastructure\b(?! software)/i],
  ['structured / solutions', /\bstructured\b|\bsolutions\b|\bstrategic capital\b/i],
  ['mid-market', /\bmid(?:dle)?[- ]market\b/i],
  ['secondaries', /\bsecondar(?:y|ies)\b/i],
];
const round1 = (value: number) => Math.round(value * 10) / 10;
const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? '' : 's'}`;

function latestRelevantEvent(account: Account, sources: Source[]): Source | undefined {
  const ids = new Set(account.eventIds);
  return publicEvidence(sources).filter(source => ids.has(source.id) && relevantEvent(source))
    .sort((a, b) => ((dateValue(b.date) ?? -Infinity) - (dateValue(a.date) ?? -Infinity)) || compare(a.id, b.id))[0];
}

const BUYING_ROLES: { id: 'champion' | 'budget' | 'ir'; label: string; max: number; head: (title: string, fn: string) => boolean; team: RegExp }[] = [
  { id: 'champion', label: 'Champion (GC or CCO)', max: 1,
    head: title => /\bgeneral counsel\b|\bchief (?:administrative and )?(?:legal|compliance) officer\b|\bco-head,? legal\b/i.test(title),
    team: /\blegal\b|\bcompliance\b|\bcounsel\b/i },
  { id: 'budget', label: 'Budget owner (CFO or COO)', max: 0.5,
    head: title => /\bchief (?:financial|operating) officer\b|\bCFO\b|\bCOO\b/i.test(title),
    team: /\bfinanc(?:e|ial)\b|\boperations?\b|\baccounting\b|\bcontroller\b/i },
  { id: 'ir', label: 'IR lead', max: 0.5,
    head: (title, fn) => /\bchief investor relations officer\b/i.test(title) || (/\b(?:head|chief)\b/i.test(title) && /\binvestor (?:relations?|services?)\b|\blimited partner\b|\bcapital formation\b|\bfundraising\b/i.test(`${title} ${fn}`)),
    team: /\binvestor (?:relations?|services?)\b|\blimited partner\b|\bcapital formation\b|\bfundraising\b/i },
];
const DEPUTY = /\b(?:deputy|associate|assistant)\s+(?:general counsel|chief \w+ officer)\b/gi;

/** Credit per buying role: named + sourced holder = full, role visible only = half, unknown = 0. */
export function buyerAccess(people: Dataset['contacts']) {
  const PREFER: Record<string, RegExp[]> = {
    champion: [/\bgeneral counsel\b(?! of\b)/i, /\bchief (?:administrative and )?legal officer\b/i, /\bchief compliance officer\b/i],
    budget: [/\bchief financial officer\b|\bCFO\b/i, /\bchief operating officer\b|\bCOO\b/i],
    ir: [/\bchief investor relations officer\b|\bglobal head\b/i, /\bhead of (?:investor relations|limited partner|capital formation)\b|\bco-head of limited partner\b/i],
  };
  const taken = new Set<string>();
  return BUYING_ROLES.map(role => {
    const rank = (title: string) => { const i = PREFER[role.id].findIndex(pattern => pattern.test(title)); return i < 0 ? 9 : i; };
    const heads = people.filter(contact => role.head(contact.title.replace(DEPUTY, ''), contact.function))
      .sort((a, b) => Number(taken.has(a.id)) - Number(taken.has(b.id)) || rank(a.title.replace(DEPUTY, '')) - rank(b.title.replace(DEPUTY, '')) || compare(a.id, b.id));
    const named = heads.find(contact => contact.titleStatus === 'official_source_role' && !!contact.url);
    if (named) taken.add(named.id);
    if (named) return { id: role.id, status: 'named' as const, points: role.max, contact: named.name,
      detail: `${role.label}: ${named.name}, named and sourced (${role.max})` };
    const stale = heads[0];
    if (stale) return { id: role.id, status: 'role' as const, points: role.max / 2, contact: stale.name,
      detail: `${role.label}: ${stale.name}, role to re-confirm (${role.max / 2})` };
    const team = people.find(contact => role.team.test(`${contact.title} ${contact.function}`));
    if (team) return { id: role.id, status: 'role' as const, points: role.max / 2, contact: null,
      detail: `${role.label}: role identified, holder not named (${role.max / 2})` };
    return { id: role.id, status: 'none' as const, points: 0, contact: null, detail: `${role.label}: not found (0)` };
  });
}

export function scoreAccount(account: Account, dataset: Dataset, state: WorkspaceState, fit: RankedAccount['fit']): AccountScore | null {
  if (account.motion !== 'net_new') return null;
  const sources = evidence(account, dataset, state);
  const linked = publicEvidence(sources);
  const asOf = dateValue(dataset.asOf);

  // Timing: a relevant, dated public fund event, decaying linearly over a year.
  const event = latestRelevantEvent(account, sources);
  const eventTime = event ? dateValue(event.date) : null;
  const days = event && eventTime !== null && asOf !== null ? Math.floor((asOf - eventTime) / DAY) : null;
  let timing = 0;
  let timingDetail = 'No relevant, dated fund event in the active sources.';
  if (event && days === null) timingDetail = 'A fund event is on file, but its date is unknown.';
  else if (event && days !== null && days >= 0 && days <= SCORE_TIMING_WINDOW_DAYS) {
    timing = round1(SCORE_WEIGHTS.timing * (1 - days / SCORE_TIMING_WINDOW_DAYS));
    timingDetail = `Fund event ${shortDate(event.date)} · ${plural(days, 'day')} before research date. Credit fades evenly to zero over ${SCORE_TIMING_WINDOW_DAYS} days.`;
  } else if (event && days !== null) timingDetail = `Last relevant fund event (${shortDate(event.date)}) is over a year old.`;

  // Fit: linked firm context, a dated fund fact, and multi-strategy complexity.
  const firm = linked.find(source => source.id === `${account.id}-context`);
  const fund = linked.find(source => source.id === `${account.id}-fund-context` && !/not established/i.test(source.text));
  const strategies = STRATEGY_TERMS.filter(([, pattern]) => pattern.test(`${account.strategy} ${firm?.text ?? ''} ${fund?.text ?? ''} ${event?.text ?? ''}`)).map(([label]) => label);
  const fitParts: string[] = [];
  let fitPoints = 0;
  if (fit !== 'Unresolved' && firm) { fitPoints += 1.5; fitParts.push('firm profile on file'); }
  if (fit !== 'Unresolved' && fund) { fitPoints += 0.75; fitParts.push('dated fund fact'); }
  if (fit !== 'Unresolved' && strategies.length >= 2) { fitPoints += 0.75; fitParts.push(`${strategies.length} strategies (${strategies.slice(0, 3).join(', ')})`); }
  const fitDetail = fit === 'Unresolved' ? 'Firm identity or profile is missing.' : fitParts.length ? `${fitParts.join(' · ').replace(/^./, first => first.toUpperCase())}.` : 'Plausible fit, thin public context.';

  // Buyer access: the three buying roles for LP-obligation work. A named, sourced holder of the
  // role earns full credit; a role we can see (someone on that team, or a holder whose role needs
  // re-confirming) earns half. Unknown roles earn nothing.
  const people = contactLeads(account, dataset, state);
  const access = buyerAccess(people);
  const reach = round1(access.reduce((sum, item) => sum + item.points, 0) * 100) / 100;
  const reachDetail = people.length ? `${access.map(item => item.detail).join(' · ')}.` : 'No researched contacts in the active sources.';

  // Evidence: enough linked sources to check, and a trigger with a primary source.
  const datedEvent = Boolean(event && eventTime !== null && event.url);
  const evidencePoints = (linked.length >= 5 ? 0.5 : 0) + (datedEvent ? 0.5 : 0);
  const evidenceDetail = `${plural(linked.length, 'public source')}${datedEvent ? ' · dated trigger with a primary source' : ' · no dated trigger to verify'}.`;

  const drivers: ScoreDriver[] = [
    { id: 'timing', label: 'Timing', points: timing, max: SCORE_WEIGHTS.timing, detail: timingDetail },
    { id: 'fit', label: 'Fit', points: round1(fitPoints), max: SCORE_WEIGHTS.fit, detail: fitDetail },
    { id: 'reach', label: 'Reach', points: reach, max: SCORE_WEIGHTS.reach, detail: reachDetail },
    { id: 'evidence', label: 'Evidence', points: evidencePoints, max: SCORE_WEIGHTS.evidence, detail: evidenceDetail },
  ];
  return { total: round1(drivers.reduce((sum, driver) => sum + driver.points, 0)), max: 10, drivers };
}

function normalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalize);
  if (record(value)) return Object.fromEntries(Object.keys(value).sort(compare).map(key => [key, normalize(value[key])]));
  return value;
}

// A stable input fingerprint, not a security or semantic-grounding guarantee.
function fingerprint(value: unknown): string {
  const text = JSON.stringify(normalize(value));
  let a = 2166136261;
  let b = 0x9e3779b9;
  for (let i = 0; i < text.length; i++) {
    a = Math.imul(a ^ text.charCodeAt(i), 16777619);
    b = Math.imul(b ^ text.charCodeAt(i), 2246822519);
  }
  return `aiw-v1-${(a >>> 0).toString(16).padStart(8, '0')}${(b >>> 0).toString(16).padStart(8, '0')}`;
}

export function createInitialState(_dataset: Dataset): WorkspaceState {
  return { version: 1, sourceOverrides: {}, plans: {}, runs: [] };
}

export function inputSignature(accountId: string, dataset: Dataset, state: WorkspaceState, policy: Policy = DEFAULT_POLICY): string {
  const account = dataset.accounts.find(item => item.id === accountId);
  if (!account) throw new Error('Account is not in this dataset.');
  const ids = unique([...account.sourceIds, ...account.eventIds]);
  return fingerprint({
    datasetVersion: dataset.version, asOf: dataset.asOf, policy,
    account: { ...account, sourceIds: unique(account.sourceIds), eventIds: unique(account.eventIds) },
    sources: ids.map(id => ({ id, active: state.sourceOverrides[id] !== false,
      source: dataset.sources.find(source => source.id === id && source.accountId === accountId) ?? null })),
    contacts: dataset.contacts.filter(contact => contact.accountId === accountId).sort((a, b) => compare(a.id, b.id)),
  });
}

export function rankAccounts(dataset: Dataset, state: WorkspaceState, policy: Policy = DEFAULT_POLICY): RankedAccount[] {
  if (!Number.isFinite(policy.warmDays) || policy.warmDays < 0) throw new Error('Warm window must be a nonnegative number.');
  const events = new Map<string, number>();
  const ranked = dataset.accounts.map(account => {
    const sources = evidence(account, dataset, state);
    const publicSources = publicEvidence(sources);
    const firmContext = publicSources.find(source => source.id === `${account.id}-context`);
    const missing: string[] = [];
    if (!account.name.trim()) missing.push('Account name is missing.');
    if (!account.domain.trim()) missing.push('Account domain is missing.');
    if (!firmContext) missing.push('Active, linked firm strategy context is missing.');
    if (dateValue(dataset.asOf) === null) missing.push('A valid evidence as-of date is missing.');
    for (const id of unique([...account.sourceIds, ...account.eventIds])) {
      if (!dataset.sources.some(source => source.id === id && source.accountId === account.id)) missing.push(`Source record missing: ${id}.`);
    }
    const fit: RankedAccount['fit'] = account.name.trim() && account.domain.trim() && firmContext ? 'Plausible' : 'Unresolved';
    const warmEvents = currentEvents(account, sources, dataset.asOf, policy);
    const event = warmEvents.find(source => source.kind === 'public') ?? warmEvents[0];
    const temperature: RankedAccount['temperature'] = event ? 'Warm' : 'Unknown';
    events.set(account.id, event ? dateValue(event.date)! : -Infinity);
    let priority: RankedAccount['priority'];
    let reason: string;
    let nextAction: string;
    if (account.motion === 'customer_hold') {
      priority = 'Hold';
      reason = `Customer on hold: ${account.holdReason || 'review with the account owner before any expansion'}`;
      nextAction = 'Fix the open issue with the account owner and customer success first; agree with the account owner before raising expansion.';
    } else if (account.motion === 'expansion') {
      priority = 'Expansion';
      reason = 'Existing customer with an expansion opportunity; confirm health and scope with the account owner. This account is outside the net-new queue.';
      nextAction = 'Confirm the customer relationship, current obligations workflow and account health before exploring expansion.';
    } else if (fit === 'Unresolved') {
      priority = 'Review';
      reason = `Evidence review required. ${missing.join(' ')}`;
      nextAction = 'Restore missing identity or linked public context before prioritizing discovery.';
    } else if (event) {
      priority = 'P1';
      const label = event.kind === 'scenario' ? 'Fictional scenario trigger' : 'Relevant public fund or operating event';
      reason = `Plausible public fit. ${label}: ${event.text} (${shortDate(event.date)}; within ${policy.warmDays} days). Timing is a discovery prompt, not verified buying intent; private pain and complexity are unknown.`;
      nextAction = 'Review the dated trigger and relevant contacts, then prepare questions about fund obligations, ownership and workflow pain.';
    } else {
      priority = 'P2';
      reason = `Plausible public fit; no active, relevant event dated within ${policy.warmDays} days. Timing, private pain and complexity are unknown. Historical or unrelated publicity does not establish current urgency.`;
      nextAction = 'Confirm current fund activity and workflow needs in discovery before asserting urgency.';
    }
    return { ...account, fit, temperature, priority, reason, nextAction,
      health: account.motion === 'net_new' ? 'Not applicable' : 'Unknown — fictional customer scenario',
      activeSourceIds: sources.map(source => source.id), missing,
      score: scoreAccount(account, dataset, state, fit) } satisfies RankedAccount;
  });
  const priorities = ['P1', 'P2', 'Review', 'Expansion', 'Hold'];
  const fits = ['High', 'Plausible', 'Low', 'Unresolved'];
  const timing = ['Hot', 'Warm', 'Cold', 'Unknown'];
  const scoreOf = (account: RankedAccount) => account.score?.total ?? -1;
  return ranked.sort((a, b) => priorities.indexOf(a.priority) - priorities.indexOf(b.priority) ||
    scoreOf(b) - scoreOf(a) ||
    fits.indexOf(a.fit) - fits.indexOf(b.fit) || timing.indexOf(a.temperature) - timing.indexOf(b.temperature) ||
    (events.get(b.id)! > events.get(a.id)! ? 1 : events.get(b.id)! < events.get(a.id)! ? -1 : 0) || compare(a.id, b.id));
}

function field(id: string, label: string, value: string, basis: Basis, sourceIds: string[] = []): PlanField {
  return { id, label, value, basis, sourceIds: unique(sourceIds), review: 'unreviewed', buyerConfirmed: false };
}

function snapshotFields(account: RankedAccount, dataset: Dataset, state: WorkspaceState): PlanField[] {
  const sources = evidence(account, dataset, state);
  const publicSources = publicEvidence(sources);
  const events = publicSources.filter(source => account.eventIds.includes(source.id)).sort((a, b) =>
    Number(relevantEvent(b)) - Number(relevantEvent(a)) ||
    ((dateValue(b.date) ?? -Infinity) - (dateValue(a.date) ?? -Infinity)) || compare(a.id, b.id));
  const event = currentEvents(account, publicSources, dataset.asOf, DEFAULT_POLICY)[0] ?? events[0];
  const excerpts = [
    { label: 'Firm context', source: publicSources.find(source => source.id === `${account.id}-context`) },
    { label: 'Fund context', source: publicSources.find(source => source.id === `${account.id}-fund-context`) },
    { label: 'Public event', source: event },
  ].filter((item): item is { label: string; source: Source } => !!item.source);
  const shown = excerpts.filter((item, index) => excerpts.findIndex(candidate => candidate.source.id === item.source.id) === index);
  const entryLimit = Math.floor((1_000 - Math.max(0, shown.length - 1) * 2) / Math.max(1, shown.length));
  const snapshot = shown.map(({ label, source }) => {
    const prefix = `${label}${source.date ? ` (${source.date})` : ' (publication date unknown)'}: `;
    const available = Math.max(1, entryLimit - prefix.length);
    const excerpt = source.text.length > available ? `${source.text.slice(0, available - 1).trimEnd()}…` : source.text;
    return `${prefix}${excerpt}`;
  }).join('\n\n');
  return [
    shown.length ? field('snapshot', 'Sourced public snapshot — excerpts', snapshot,
      'fact', shown.map(item => item.source.id)) : field('snapshot', 'Public snapshot', 'No active firm context, fund context or public event is available. Public context is unknown.', 'unknown'),
    field('demo_motion', 'Fictional demo motion', `Fictional demo motion: ${account.motion.replaceAll('_', ' ')}. This label does not establish a real customer relationship, pipeline stage or buying intent.`,
      'scenario', sources.filter(source => source.kind === 'scenario').map(source => source.id)),
  ];
}

export function draftPlan(account: RankedAccount, dataset: Dataset, state: WorkspaceState): Plan {
  const current = rankAccounts(dataset, state).find(item => item.id === account.id);
  if (!current) throw new Error('Account is not in this dataset.');
  const ids = publicEvidence(evidence(current, dataset, state)).map(source => source.id);
  const people = contactLeads(current, dataset, state).slice(0, 3);
  const conditional = ids.length ? 'hypothesis' : 'unknown';
  const fields = [...snapshotFields(current, dataset, state),
    field('goals', 'Goals to test', ids.length ? 'Hypothesis to test: if fund obligations are a current priority, a shared view of LP commitments and deadlines may be useful. Ask which outcomes matter.' : 'Current goals are unknown. Restore public context and ask what outcomes matter.', conditional, ids),
    field('pain', 'Private pain and complexity', 'Private workflow pain, complexity and urgency are unknown. Ask how obligations are tracked and where the process is difficult.', 'unknown'),
    field('people', 'People and authority', `Buying authority, budget ownership and the current buying group are unknown.${people.length ? ` Entry-role hypothesis, using public research leads to verify: ${people.map(contact => `${contact.name} (${contact.title})`).join('; ')}. Published titles do not establish buying authority.` : ' No researched contact leads are available.'}`, 'unknown'),
    field('strategy', 'Discovery approach', ids.length ? 'Consider testing whether the public fund context creates a need to track side letters, MFN elections and reporting deadlines. Confirm the current process before proposing a solution.' : 'A supported discovery approach is unknown until public context is available.', conditional, ids),
    field('next_action', 'Next action for seller review', ids.length ? `Consider this proposed next step: ${current.nextAction}` : 'Next action is unknown pending evidence review. Restore missing identity or public context first.', conditional, ids),
    field('budget', 'Budget and decision process', 'Budget, procurement steps, decision criteria and timing are unknown; confirm them with the buyer.', 'unknown'),
  ];
  return { accountId: current.id, fields, questions: unique([...current.discoveryQuestions,
    'Who owns the obligation process, and who approves a change?',
    'What would need to be true for this to become a current priority?']),
    actions: [current.nextAction, 'Review each draft field and confirm unknowns in discovery. No message is sent and no pipeline stage changes.'],
    signature: inputSignature(current.id, dataset, state), approvedSignature: null, generatedBy: 'template', generatedAt: now() };
}

export function reviewField(state: WorkspaceState, accountId: string, fieldId: string, review: Review, value?: string): WorkspaceState {
  if (!REVIEWS.includes(review)) throw new Error('Unsupported review decision.');
  const plan = own(state.plans, accountId) ? state.plans[accountId] : undefined;
  if (!plan || !plan.fields.some(item => item.id === fieldId)) throw new Error('Draft field was not found.');
  if (review === 'edited' && !string(value)) throw new Error('An edited field needs a nonempty value.');
  const fields = plan.fields.map(item => item.id === fieldId ? { ...item, review,
    value: review === 'edited' ? value! : item.value,
    ...(review === 'unreviewed' ? { reviewedAt: undefined } : { reviewedAt: now() }), buyerConfirmed: false as const } : item);
  return { ...state, plans: { ...state.plans, [accountId]: { ...plan, fields, approvedSignature: null } } };
}

function invalidate(plan: Plan, staleFacts: boolean): Plan {
  return { ...plan, approvedSignature: null, fields: plan.fields.map(item => ({ ...item,
    ...(staleFacts && item.basis === 'fact' ? { basis: 'unknown' as const,
      value: `Stale public snapshot — regenerate and verify against current evidence. Previous draft:\n${item.value}` } : {}),
    review: 'unreviewed' as const, reviewedAt: undefined, buyerConfirmed: false as const })) };
}

export function setSourceActive(state: WorkspaceState, sourceId: string, active: boolean, dataset?: Dataset): WorkspaceState {
  if (typeof active !== 'boolean' || !sourceId) throw new Error('A source and boolean active state are required.');
  if ((state.sourceOverrides[sourceId] !== false) === active) return state;
  const source = dataset?.sources.find(item => item.id === sourceId);
  const plans = Object.fromEntries(Object.entries(state.plans).map(([id, plan]) => {
    const account = dataset?.accounts.find(item => item.id === id);
    const affected = !dataset || source?.accountId === id || account?.sourceIds.includes(sourceId) ||
      account?.eventIds.includes(sourceId) || plan.fields.some(item => item.sourceIds.includes(sourceId));
    return [id, affected ? invalidate(plan, true) : plan];
  }));
  return { ...state, sourceOverrides: { ...state.sourceOverrides, [sourceId]: active }, plans };
}

export function approvePlan(state: WorkspaceState, accountId: string, dataset: Dataset): WorkspaceState {
  const plan = own(state.plans, accountId) ? state.plans[accountId] : undefined;
  if (!plan) throw new Error('Create a draft before approving it.');
  const signature = inputSignature(accountId, dataset, state);
  if (plan.signature !== signature) throw new Error('Evidence or policy changed. Regenerate the draft before approving it.');
  if (!supportedFieldBases(plan.fields)) throw new Error('Core plan fields must preserve hypothesis or unknown status. Only the public snapshot can be factual and the demo motion can be a scenario.');
  if (!REQUIRED_FIELDS.every(id => plan.fields.some(item => item.id === id)) ||
      !plan.fields.every(item => item.review === 'accepted' || item.review === 'edited')) {
    throw new Error('Review every field and revise rejected fields before approving the plan.');
  }
  const active = new Set(rankAccounts(dataset, state).find(item => item.id === accountId)?.activeSourceIds);
  const publicIds = new Set(publicEvidence(dataset.sources).map(source => source.id));
  if (plan.fields.some(item => item.sourceIds.some(id => !active.has(id)) || item.basis === 'fact' &&
      (!item.sourceIds.length || item.sourceIds.some(id => !publicIds.has(id))))) {
    throw new Error('A draft field references missing or disabled evidence.');
  }
  return { ...state, plans: { ...state.plans, [accountId]: { ...plan, approvedSignature: signature } } };
}

function reviewedState(plan: Plan | undefined, signature: string): string {
  if (!plan) return 'No draft';
  if (plan.signature !== signature) return 'Stale draft — regenerate and review';
  if (plan.approvedSignature === signature) return 'Reviewed plan — seller review, not buyer confirmation';
  if (plan.fields.some(item => item.review === 'rejected')) return 'Rejected field — revise draft';
  return `${plan.fields.filter(item => item.review === 'accepted' || item.review === 'edited').length}/${plan.fields.length} fields reviewed; plan not approved`;
}

export function makeBrief(dataset: Dataset, state: WorkspaceState, cadence: 'daily' | 'weekly'): Brief {
  const ranked = rankAccounts(dataset, state);
  const item = (account: RankedAccount): BriefItem => {
    const contact = contactLeads(account, dataset, state)[0];
    return { accountId: account.id, name: account.name, priority: account.priority, reason: account.reason,
      nextAction: account.nextAction, contact: contact ? `${contact.name} — ${contact.title}; entry-role hypothesis; verify current role and authority` : 'No researched contact; authority unknown',
      review: reviewedState(state.plans[account.id], inputSignature(account.id, dataset, state)) };
  };
  const eligible = (account: RankedAccount) => account.motion === 'net_new' && (account.priority === 'P1' || account.priority === 'P2');
  const items = ranked.filter(eligible).slice(0, 5).map(item);
  const exceptions = ranked.filter(account => !eligible(account)).map(item);
  let changeNote = 'No previous saved brief exists; change since a prior brief is unknown.';
  if (state.previousBrief) {
    const previous = new Map([...state.previousBrief.items, ...state.previousBrief.exceptions].map(value => [value.accountId, value]));
    const current = new Map([...items, ...exceptions].map(value => [value.accountId, value]));
    let added = 0, changed = 0, removed = 0;
    for (const [id, value] of current) {
      if (!previous.has(id)) added++;
      else if (JSON.stringify(normalize(previous.get(id))) !== JSON.stringify(normalize(value))) changed++;
    }
    for (const id of previous.keys()) if (!current.has(id)) removed++;
    changeNote = added || changed || removed ? `Compared with the previous saved brief: ${added} added, ${changed} changed, ${removed} removed from the displayed records. These are brief changes, not measured sales outcomes.` :
      'No changes to the displayed priority, action, contact or review records since the previous saved brief. Other evidence changes are not inferred.';
  }
  return { cadence, asOf: dataset.asOf, items, exceptions, changeNote };
}

export function validateModelPlan(raw: unknown, account: RankedAccount, dataset: Dataset, state: WorkspaceState): Plan {
  if (!record(raw) || raw.account_id !== account.id) throw new Error('AI response has the wrong account identity.');
  if (!Array.isArray(raw.fields) || raw.fields.length < REQUIRED_FIELDS.length || raw.fields.length > 20) throw new Error('AI response must contain the required plan fields.');
  const current = rankAccounts(dataset, state).find(item => item.id === account.id);
  if (!current) throw new Error('Account is not in this dataset.');
  const active = new Map(evidence(current, dataset, state).map(source => [source.id, source]));
  const seen = new Set<string>();
  const fields = raw.fields.map((value): PlanField => {
    if (!record(value) || !string(value.id, 64) || !/^[a-z][a-z0-9_-]*$/.test(value.id) ||
      ['snapshot', 'demo_motion'].includes(value.id) || seen.has(value.id) || !string(value.label, 160) || !string(value.value, 6_000) ||
      !['hypothesis', 'unknown'].includes(value.basis as string) || !Array.isArray(value.source_ids) ||
      !value.source_ids.every(id => typeof id === 'string') || new Set(value.source_ids).size !== value.source_ids.length) {
      throw new Error('AI response contains an invalid, duplicated or unsupported field.');
    }
    seen.add(value.id);
    wording(value.label, value.value);
    const ids = value.source_ids as string[];
    if (ids.some(id => !active.has(id))) throw new Error('AI field references missing, disabled or cross-account evidence.');
    if (value.basis === 'hypothesis') {
      if (!ids.length) throw new Error('Each AI hypothesis needs active evidence references.');
      if (!/^\s*(?:hypothesis\b|if\b|ask\b|consider\b|explore\b|confirm\b|validate\b|test\b|check\b|propos(?:e|ed)\b|suggest\b|(?:could|would|should|might|may|is|are|does|do|what|which|who|how|when|where)\b[\s\S]*\?)/i.test(value.value)) {
        throw new Error('AI hypotheses must be phrased as a conditional suggestion, hypothesis or discovery question.');
      }
    } else if (!/unknown|unconfirmed|not (?:yet )?(?:known|confirmed|established|verified|provided|available)|to be confirmed|\bTBD\b/i.test(value.value)) {
      throw new Error('Unknown AI fields must preserve uncertainty explicitly.');
    }
    return field(value.id, lpTerms(value.label), lpTerms(value.value), value.basis as Basis, ids);
  });
  if (!REQUIRED_FIELDS.every(id => seen.has(id))) throw new Error('AI response is missing goals, pain, people, strategy or next_action.');
  const readList = (value: unknown, label: string): string[] => {
    if (!Array.isArray(value) || !value.length || value.length > 20 || !value.every(item => string(item, 2_000))) throw new Error(`AI ${label} must be a nonempty list of text.`);
    wording(...(value as string[]));
    return (value as string[]).map(lpTerms);
  };
  const questions = readList(raw.questions, 'questions');
  const proposedActions = readList(raw.actions, 'actions');
  // The fixed hold policy governs action suggestions even if model text ignores it.
  const safeFields = current.motion === 'customer_hold' ? fields.map(item => item.id === 'next_action' ?
    field('next_action', 'Fix the open issue first',
      `Unknown: whether the customer is ready to talk about more scope. ${current.nextAction}`, 'unknown') : item) : fields;
  const actions = current.motion === 'customer_hold' ? [current.nextAction] : proposedActions;
  // Optional email: one sourced contact of this account, greeted by name, short, no internal wording.
  let email: Plan['email'];
  if (raw.email !== undefined) {
    const value = raw.email;
    if (!record(value) || !string(value.contact_id, 96) || !string(value.subject, 80) || !string(value.body, 900)) throw new Error('AI email is malformed.');
    const contactId = (value.contact_id as string).replace(/-profile$/, '');
    const contact = dataset.contacts.find(item => item.id === contactId && item.accountId === current.id);
    if (!contact || !active.has(`${contactId}-profile`)) throw new Error('AI email is addressed to someone outside this account\'s sourced contacts.');
    const greeting = /^Hi ([^,\n]{1,40}),/.exec(value.body as string);
    if (!greeting || !contact.name.toLowerCase().includes(greeting[1].trim().toLowerCase())) throw new Error('AI email must greet the chosen contact by name.');
    if (EMAIL_TRACKING.test(`${value.subject} ${value.body}`)) throw new Error('AI email must not mention the buyer\'s page views, visits or email opens.');
    wording(value.subject as string, value.body as string);
    email = { contactId, subject: lpTerms(value.subject as string), body: greetingLine(lpTerms(value.body as string)) };
  }
  return { accountId: current.id, fields: [...snapshotFields(current, dataset, state), ...safeFields], questions, actions,
    signature: inputSignature(current.id, dataset, state), approvedSignature: null, generatedBy: 'deepseek', generatedAt: now(), ...(email ? { email } : {}) };
}

export function restoreState(value: unknown, dataset: Dataset): WorkspaceState {
  const state = createInitialState(dataset);
  if (!record(value) || value.version !== 1) return state;
  if (record(value.sourceOverrides)) for (const source of dataset.sources) {
    if (own(value.sourceOverrides, source.id) && typeof value.sourceOverrides[source.id] === 'boolean') {
      state.sourceOverrides[source.id] = value.sourceOverrides[source.id] as boolean;
    }
  }
  if (record(value.plans)) for (const account of dataset.accounts) {
    const raw = own(value.plans, account.id) ? value.plans[account.id] : undefined;
    if (!record(raw) || raw.accountId !== account.id || !string(raw.signature, 200) ||
      !['template', 'deepseek'].includes(raw.generatedBy as string) || !string(raw.generatedAt, 100) || dateValue(raw.generatedAt) === null ||
      !Array.isArray(raw.fields) || raw.fields.length < REQUIRED_FIELDS.length || raw.fields.length > 30 ||
      !Array.isArray(raw.questions) || !raw.questions.every(item => string(item, 2_000)) ||
      !Array.isArray(raw.actions) || !raw.actions.every(item => string(item, 2_000))) continue;
    const seen = new Set<string>();
    const fields: PlanField[] = [];
    let valid = true;
    for (const item of raw.fields) {
      if (!record(item) || !string(item.id, 64) || seen.has(item.id) || !string(item.label, 160) || !string(item.value, 100_000) ||
        !BASES.includes(item.basis as Basis) || !REVIEWS.includes(item.review as Review) || !Array.isArray(item.sourceIds) ||
        !item.sourceIds.every(id => string(id, 200)) || (item.review === 'edited' && !string(item.value))) { valid = false; break; }
      seen.add(item.id);
      fields.push({ id: item.id, label: item.label, value: item.value, basis: item.basis as Basis,
        sourceIds: unique(item.sourceIds as string[]), review: item.review as Review, buyerConfirmed: false,
        ...(typeof item.reviewedAt === 'string' && dateValue(item.reviewedAt) !== null ? { reviewedAt: item.reviewedAt } : {}) });
    }
    if (!valid || !supportedFieldBases(fields)) continue;
    let plan: Plan = { accountId: account.id, fields, questions: raw.questions as string[], actions: raw.actions as string[],
      signature: raw.signature, approvedSignature: null, generatedBy: raw.generatedBy as Plan['generatedBy'], generatedAt: raw.generatedAt };
    const signature = inputSignature(account.id, dataset, state);
    const active = new Set(evidence(account, dataset, state).map(source => source.id));
    const publicIds = new Set(publicEvidence(evidence(account, dataset, state)).map(source => source.id));
    const unsafeSource = fields.some(item => item.sourceIds.some(id => !active.has(id)) || item.basis === 'fact' &&
      (!item.sourceIds.length || item.sourceIds.some(id => !publicIds.has(id))));
    if (plan.signature !== signature || unsafeSource) plan = invalidate(plan, true);
    else if (raw.approvedSignature === signature && fields.every(item => item.review === 'accepted' || item.review === 'edited')) plan.approvedSignature = signature;
    state.plans[account.id] = plan;
  }
  if (Array.isArray(value.runs)) state.runs = value.runs.slice(-200).flatMap((item): RunRecord[] => {
    if (!record(item) || !string(item.id, 200) || !dataset.accounts.some(account => account.id === item.accountId) ||
      !string(item.startedAt, 100) || dateValue(item.startedAt) === null || typeof item.elapsedMs !== 'number' ||
      !Number.isFinite(item.elapsedMs) || item.elapsedMs < 0 || !['success', 'failed'].includes(item.status as string) || !string(item.provider, 100)) return [];
    return [{ id: item.id, accountId: item.accountId as string, startedAt: item.startedAt, elapsedMs: item.elapsedMs,
      status: item.status as RunRecord['status'], provider: item.provider,
      ...(typeof item.error === 'string' ? { error: item.error.slice(0, 2_000) } : {}),
      ...Object.fromEntries(['inputTokens', 'outputTokens'].filter(key => typeof item[key] === 'number' && Number.isInteger(item[key]) && (item[key] as number) >= 0).map(key => [key, item[key]])) }];
  });
  const brief = value.previousBrief;
  if (record(brief) && ['daily', 'weekly'].includes(brief.cadence as string) && string(brief.asOf, 100) &&
    string(brief.changeNote, 4_000) && Array.isArray(brief.items) && Array.isArray(brief.exceptions)) {
    const validItem = (item: unknown): item is BriefItem => record(item) &&
      dataset.accounts.some(account => account.id === item.accountId) &&
      ['accountId', 'name', 'priority', 'reason', 'nextAction', 'contact', 'review'].every(key => string(item[key], 24_000));
    if (brief.items.every(validItem) && brief.exceptions.every(validItem)) state.previousBrief = {
      cadence: brief.cadence as Brief['cadence'], asOf: brief.asOf, changeNote: brief.changeNote,
      items: brief.items.map(item => ({ ...item })), exceptions: brief.exceptions.map(item => ({ ...item })),
    };
  }
  return state;
}
