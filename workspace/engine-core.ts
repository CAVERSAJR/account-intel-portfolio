// Engine factory for the Pearl Navy workspace (app/index.html).
// Exposes the same tested domain logic the React build uses, so the score,
// source toggles and AI-response validation are not reimplemented by hand.
import type { Dataset, WorkspaceState } from './types';
import {
  SCORE_TIMING_WINDOW_DAYS, SCORE_WEIGHTS, createInitialState, inputSignature,
  buyerAccess, rankAccounts, setSourceActive, validateModelPlan,
} from './domain';


// Pearl workspace ids → research dataset ids.
const ID_MAP_INTERNAL: Record<string, string> = {
  advent: 'advent_international', audax: 'audax', francisco: 'francisco_partners', gi: 'gi_partners',
  gtcr: 'gtcr', summit: 'summit', thoma: 'thoma_bravo', vista: 'vista_equity_partners', ta: 'ta', hggc: 'hggc', battery: 'battery_ventures',
};

export function createEngine(dataset: Dataset) {
let state: WorkspaceState = createInitialState(dataset);
const STORE = 'account-intel-engine-v1';
try {
  const saved = JSON.parse(localStorage.getItem(STORE) || 'null');
  if (saved && typeof saved === 'object') for (const [id, on] of Object.entries(saved)) {
    if (typeof on === 'boolean' && dataset.sources.some(source => source.id === id)) state.sourceOverrides[id] = on;
  }
} catch { /* storage unavailable: session-only */ }
const save = () => { try { localStorage.setItem(STORE, JSON.stringify(state.sourceOverrides)); } catch { /* session-only */ } };

const ranked = () => rankAccounts(dataset, state);
const find = (pearlId: string) => ranked().find(account => account.id === (ID_MAP_INTERNAL[pearlId] ?? pearlId));

const engine = {
  asOf: dataset.asOf,
  weights: SCORE_WEIGHTS,
  timingWindowDays: SCORE_TIMING_WINDOW_DAYS,
  account: find,
  score: (pearlId: string) => find(pearlId)?.score ?? null,
  eventSource(pearlId: string) {
    const account = dataset.accounts.find(item => item.id === ID_MAP_INTERNAL[pearlId]);
    const id = account?.eventIds[0];
    const source = dataset.sources.find(item => item.id === id);
    return source ? { ...source, active: state.sourceOverrides[source.id] !== false } : null;
  },
  sources(pearlId: string) {
    return dataset.sources.filter(source => source.accountId === ID_MAP_INTERNAL[pearlId])
      .map(source => ({ ...source, active: state.sourceOverrides[source.id] !== false }));
  },
  setSource(sourceId: string, active: boolean) { state = setSourceActive(state, sourceId, active, dataset); save(); },
  // Research volume behind the workspace (used by the time-back estimate).
  stats: () => ({ accounts: dataset.accounts.length, sources: dataset.sources.filter(source => source.kind === 'public').length, contacts: dataset.contacts.length }),
  contactCount: (pearlId: string) => dataset.contacts.filter(contact => contact.accountId === ID_MAP_INTERNAL[pearlId]).length,
  // Named, sourced contacts for an account: the three buying-role holders first, then the rest. No addresses.
  contacts(pearlId: string) {
    const people = dataset.contacts.filter(contact => contact.accountId === ID_MAP_INTERNAL[pearlId]);
    const access = buyerAccess(people);
    const lead = (name: string) => { const i = access.findIndex(item => item.contact === name); return i < 0 ? 9 : i; };
    return [...people].sort((a, b) => lead(a.name) - lead(b.name)).map(contact => ({ id: contact.id, name: contact.name, title: contact.title,
      function: contact.function, url: contact.url, role: access.find(item => item.contact === contact.name)?.id ?? null, status: contact.titleStatus, checked: contact.researchedAt }));
  },
  access: (pearlId: string) => buyerAccess(dataset.contacts.filter(contact => contact.accountId === ID_MAP_INTERNAL[pearlId])),
  source(sourceId: string) {
    const source = dataset.sources.find(item => item.id === sourceId);
    return source ? { ...source, active: state.sourceOverrides[source.id] !== false } : null;
  },
  // Pure what-if: the score this account would have with one source excluded. Does not change state.
  scoreWithout(pearlId: string, sourceId: string) {
    const scratch = setSourceActive(state, sourceId, false, dataset);
    return rankAccounts(dataset, scratch).find(account => account.id === (ID_MAP_INTERNAL[pearlId] ?? pearlId))?.score ?? null;
  },
  reset() { state = createInitialState(dataset); save(); },
  signature: (pearlId: string) => inputSignature(ID_MAP_INTERNAL[pearlId], dataset, state),
  // The exact request body the local server accepts (it re-checks every record against its own copy).
  request(pearlId: string, product: string, recipientId?: string) {
    const account = find(pearlId);
    if (!account) throw new Error('Account is not in the research dataset.');
    const evidence = dataset.sources.filter(source => source.accountId === account.id && state.sourceOverrides[source.id] !== false);
    // The seller's chosen contact, if that contact's profile is among the active sources.
    const recipient = recipientId && evidence.some(source => source.id === `${recipientId}-profile`) ? `${recipientId}-profile` : null;
    return {
      body: { account_id: account.id, as_of: dataset.asOf, evidence: evidence.map(({ id, text, date, kind }) => ({ id, text, date, kind })),
        context: { name: account.name, strategy: account.strategy, fundContext: account.fundContext, product, ...(recipient ? { recipient } : {}) } },
      sources: evidence.length, recipient: recipient ? recipientId! : null,
    };
  },
  validate(pearlId: string, raw: unknown) {
    const account = find(pearlId);
    if (!account) throw new Error('Account is not in the research dataset.');
    return validateModelPlan(raw, account, dataset, state);
  },
};

return engine;
}
