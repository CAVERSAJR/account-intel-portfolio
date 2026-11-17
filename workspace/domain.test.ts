import { describe, expect, it } from 'vitest';
import prepared from './data.json';
import { DEFAULT_POLICY, type Account, type Dataset, type ModelResponse, type Source, type WorkspaceState } from './types';
import { approvePlan, createInitialState, draftPlan, inputSignature, makeBrief, rankAccounts, restoreState, reviewField, setSourceActive, validateModelPlan, buyerAccess } from './domain';

function account(id = 'alpha', patch: Partial<Account> = {}): Account {
  return { id, name: `Firm ${id}`, domain: `${id}.example`, strategy: 'Private markets investing',
    fundContext: 'Current fund context needs verification', fitBasis: 'Public context only',
    motion: 'net_new', motionSynthetic: true, holdReason: null,
    sourceIds: [`${id}-context`, `${id}-event`], eventIds: [`${id}-event`], discoveryQuestions: ['Who owns obligations?'], ...patch };
}

function source(id: string, accountId: string, patch: Partial<Source> = {}): Source {
  return { id, accountId, title: 'Public firm context', text: 'Private equity fund manager.',
    url: `https://${accountId}.example/research`, date: null, kind: 'public', ...patch };
}

function fixture(): Dataset {
  return { version: 'test-v1', asOf: '2026-11-12', accounts: [account()], contacts: [], sources: [
    source('alpha-context', 'alpha'),
    source('alpha-event', 'alpha', { title: 'Fund close', text: 'Closed Fund IX at $2 billion.', date: '2026-10-27' }),
  ] };
}

function withDraft(dataset: Dataset): WorkspaceState {
  const state = createInitialState(dataset);
  const ranked = rankAccounts(dataset, state)[0];
  return { ...state, plans: { [ranked.id]: draftPlan(ranked, dataset, state) } };
}

function reviewAll(state: WorkspaceState, id = 'alpha'): WorkspaceState {
  for (const field of state.plans[id].fields) state = reviewField(state, id, field.id, 'accepted');
  return state;
}

function model(): ModelResponse {
  return { account_id: 'alpha', fields: [
    { id: 'goals', label: 'Goals', value: 'Hypothesis: fund reporting may need a shared workflow.', basis: 'hypothesis', source_ids: ['alpha-event'] },
    { id: 'pain', label: 'Pain', value: 'Private pain and complexity are unknown.', basis: 'unknown', source_ids: [] },
    { id: 'people', label: 'People', value: 'Buying authority is unknown.', basis: 'unknown', source_ids: [] },
    { id: 'strategy', label: 'Strategy', value: 'Ask how the team tracks obligations today.', basis: 'hypothesis', source_ids: ['alpha-context'] },
    { id: 'next_action', label: 'Next action', value: 'Consider confirming the current reporting process.', basis: 'hypothesis', source_ids: ['alpha-event'] },
  ], questions: ['Who owns obligation tracking?'], actions: ['Prepare discovery questions for seller review.'] };
}

describe('evidence-based queue', () => {
  it('uses fresh relevant fund timing, and demotes when its source is disabled', () => {
    const dataset = fixture();
    const initial = createInitialState(dataset);
    const ranked = rankAccounts(dataset, initial)[0];
    expect(ranked).toMatchObject({ fit: 'Plausible', temperature: 'Warm', priority: 'P1', health: 'Not applicable' });
    const disabled = rankAccounts(dataset, setSourceActive(initial, 'alpha-event', false, dataset))[0];
    expect(disabled).toMatchObject({ fit: 'Plausible', temperature: 'Unknown', priority: 'P2' });
    expect(disabled.activeSourceIds).not.toContain('alpha-event');
    expect(disabled.reason).toContain('unknown');
  });

  it.each([
    { label: 'unrelated acquisition', date: '2026-11-01', text: 'Portfolio company announced an acquisition of a software business.' },
    { label: 'fund-mentioned portfolio acquisition', date: '2026-11-01', text: 'Fund VIII closed the acquisition of a software business.' },
    { label: 'stale fund event', date: '2026-07-23', text: 'Closed Fund IX.' },
    { label: 'undated fund event', date: null, text: 'Closed Fund IX.' },
    { label: 'future fund event', date: '2027-01-01', text: 'Closed Fund IX.' },
    { label: 'invalid calendar date', date: '2026-02-30', text: 'Closed Fund IX.' },
  ])('preserves Unknown timing for $label', ({ date, text }) => {
    const dataset = fixture();
    dataset.sources[1] = { ...dataset.sources[1], title: 'Public announcement', date, text };
    expect(rankAccounts(dataset, createInitialState(dataset))[0]).toMatchObject({ temperature: 'Unknown', priority: 'P2' });
  });

  it('uses the 90-day boundary and only explicit event IDs', () => {
    const dataset = fixture();
    dataset.sources[1].date = '2026-08-14';
    expect(rankAccounts(dataset, createInitialState(dataset))[0].priority).toBe('P1');
    dataset.sources[1].date = '2026-08-13';
    expect(rankAccounts(dataset, createInitialState(dataset))[0].temperature).toBe('Unknown');
    dataset.sources[1].date = '2026-11-01';
    dataset.accounts[0].eventIds = [];
    expect(rankAccounts(dataset, createInitialState(dataset))[0].priority).toBe('P2');
  });

  it('keeps customer holds and expansion outside the prospect queue regardless of timing', () => {
    const dataset = fixture();
    dataset.accounts.push(account('hold', { motion: 'customer_hold', holdReason: 'Open service escalation' }), account('expansion', { motion: 'expansion' }));
    const state = createInitialState(dataset);
    const ranked = rankAccounts(dataset, state);
    expect(ranked.find(item => item.id === 'hold')).toMatchObject({ priority: 'Hold' });
    expect(ranked.find(item => item.id === 'expansion')).toMatchObject({ priority: 'Expansion' });
    expect(ranked.find(item => item.id === 'hold')?.reason).toBe('Customer on hold: Open service escalation');
    const brief = makeBrief(dataset, state, 'daily');
    expect(brief.items.map(item => item.accountId)).toEqual(['alpha']);
    expect(brief.exceptions.map(item => item.priority).sort()).toEqual(['Expansion', 'Hold']);
  });

  it('labels scenario timing fictional without treating scenario-only context as public fit', () => {
    const dataset = fixture();
    dataset.sources[1] = { ...dataset.sources[1], kind: 'scenario', url: null, title: 'Fictional fund trigger' };
    const state = createInitialState(dataset);
    expect(rankAccounts(dataset, state)[0]).toMatchObject({ priority: 'P1', temperature: 'Warm' });
    expect(rankAccounts(dataset, state)[0].reason).toContain('Fictional scenario trigger');
    expect(rankAccounts(dataset, setSourceActive(state, 'alpha-context', false, dataset))[0]).toMatchObject({ fit: 'Unresolved', priority: 'Review' });
  });

  it('requires identity and linked public context; does not manufacture High fit', () => {
    const dataset = fixture();
    dataset.accounts[0].domain = '';
    expect(rankAccounts(dataset, createInitialState(dataset))[0]).toMatchObject({ fit: 'Unresolved', priority: 'Review' });
    dataset.accounts[0].domain = 'alpha.example';
    dataset.sources.forEach(item => { item.url = null; });
    expect(rankAccounts(dataset, createInitialState(dataset))[0].fit).toBe('Unresolved');
  });

  it('does not let contact profiles or a fund event substitute for disabled firm context', () => {
    const dataset = fixture();
    dataset.accounts[0].sourceIds.push('lead-profile');
    dataset.sources.push(source('lead-profile', 'alpha', { title: 'Alex — professional profile', text: 'Alex is chief financial officer for private equity funds.' }));
    const disabled = setSourceActive(createInitialState(dataset), 'alpha-context', false, dataset);
    expect(rankAccounts(dataset, disabled)[0]).toMatchObject({ fit: 'Unresolved', priority: 'Review' });
    expect(rankAccounts(dataset, disabled)[0].missing).toContain('Active, linked firm strategy context is missing.');
    expect(rankAccounts(dataset, disabled)[0].activeSourceIds).toContain('lead-profile');
  });

  it('does not inflate priority or reorder ties from duplicate event references', () => {
    const dataset = fixture();
    dataset.accounts[0].eventIds.push('alpha-event', 'alpha-event');
    dataset.accounts.push(account('beta'));
    dataset.sources.push(source('beta-context', 'beta'), source('beta-event', 'beta', { text: 'Closed Fund VI.', date: '2026-10-27' }));
    const state = createInitialState(dataset);
    expect(rankAccounts(dataset, state).map(item => item.id)).toEqual(['alpha', 'beta']);
    dataset.accounts.reverse(); dataset.sources.reverse();
    expect(rankAccounts(dataset, state).map(item => item.id)).toEqual(['alpha', 'beta']);
  });
});

describe('current inputs and local review', () => {
  it('signs source content, contact data, date and policy while normalizing source ordering', () => {
    const dataset = fixture(), state = createInitialState(dataset);
    const original = inputSignature('alpha', dataset, state);
    dataset.sources.reverse(); dataset.accounts[0].sourceIds.reverse();
    expect(inputSignature('alpha', dataset, state)).toBe(original);
    dataset.sources[0].text += ' Updated wording.';
    expect(inputSignature('alpha', dataset, state)).not.toBe(original);
    expect(inputSignature('alpha', fixture(), state, { ...DEFAULT_POLICY, version: 'changed' })).not.toBe(original);
    const dated = fixture(); dated.asOf = '2026-11-13';
    expect(inputSignature('alpha', dated, state)).not.toBe(original);
    const contact = fixture();
    contact.contacts.push({ id: 'c1', accountId: 'alpha', name: 'Alex', title: 'CFO', function: 'finance', url: null, linkedin: null, email: 'alex@demo.invalid', emailVerified: false, titleStatus: 'unverified', researchedAt: '2026-11-12', uncertainty: 'Authority unknown' });
    expect(inputSignature('alpha', contact, state)).not.toBe(original);
  });

  it('requires all fields reviewed and a fresh signature before approval', () => {
    const dataset = fixture();
    let state = withDraft(dataset);
    expect(() => approvePlan(state, 'alpha', dataset)).toThrow(/Review every field/);
    state = reviewAll(state);
    state = reviewField(state, 'alpha', 'pain', 'rejected');
    expect(() => approvePlan(state, 'alpha', dataset)).toThrow(/rejected/);
    state = reviewField(state, 'alpha', 'pain', 'edited', 'Pain is unknown; ask for one concrete workflow example.');
    const approved = approvePlan(state, 'alpha', dataset);
    expect(approved.plans.alpha.approvedSignature).toBe(approved.plans.alpha.signature);
    expect(approved.plans.alpha.fields.every(item => item.buyerConfirmed === false)).toBe(true);
    const changed = structuredClone(dataset); changed.sources[0].text += ' Revised';
    expect(() => approvePlan(approved, 'alpha', changed)).toThrow(/changed/);
  });

  it('persists edited decisions and seller approval without making them buyer-confirmed', () => {
    const dataset = fixture();
    let state = reviewAll(withDraft(dataset));
    state = reviewField(state, 'alpha', 'people', 'edited', 'Decision owner is unknown; verify who owns LP reporting.');
    state = approvePlan(state, 'alpha', dataset);
    const restored = restoreState(JSON.parse(JSON.stringify(state)), dataset);
    expect(restored.plans.alpha.approvedSignature).toBe(state.plans.alpha.signature);
    expect(restored.plans.alpha.fields.find(item => item.id === 'people')).toMatchObject({ review: 'edited', value: 'Decision owner is unknown; verify who owns LP reporting.', buyerConfirmed: false });
    expect(makeBrief(dataset, restored, 'daily').items[0].review).toContain('not buyer confirmation');
  });

  it('invalidates reviews and factual support on source removal, including after reload', () => {
    const dataset = fixture();
    const approved = approvePlan(reviewAll(withDraft(dataset)), 'alpha', dataset);
    const changed = setSourceActive(approved, 'alpha-event', false, dataset);
    expect(changed.plans.alpha.approvedSignature).toBeNull();
    expect(changed.plans.alpha.fields.every(item => item.review === 'unreviewed')).toBe(true);
    expect(changed.plans.alpha.fields.find(item => item.id === 'snapshot')?.basis).toBe('unknown');
    expect(() => approvePlan(reviewAll(changed), 'alpha', dataset)).toThrow(/changed/);
    const restored = restoreState(JSON.parse(JSON.stringify(changed)), dataset);
    expect(restored.plans.alpha.approvedSignature).toBeNull();
    expect(makeBrief(dataset, restored, 'daily').items[0].review).toContain('Stale');
    const regenerated = draftPlan(rankAccounts(dataset, restored)[0], dataset, restored);
    expect(regenerated.fields.filter(item => item.basis === 'fact').flatMap(item => item.sourceIds)).not.toContain('alpha-event');
    expect(regenerated.signature).not.toBe(approved.plans.alpha.signature);
  });

  it('invalidates imported review when evidence content or policy identity changed', () => {
    const dataset = fixture();
    const approved = approvePlan(reviewAll(withDraft(dataset)), 'alpha', dataset);
    const changed = structuredClone(dataset); changed.sources[0].text += ' Changed public research.';
    const restored = restoreState(approved, changed);
    expect(restored.plans.alpha.approvedSignature).toBeNull();
    expect(restored.plans.alpha.fields.every(item => item.review === 'unreviewed')).toBe(true);
    expect(restored.plans.alpha.fields.find(item => item.id === 'snapshot')?.basis).toBe('unknown');
  });

  it('uses conservative global invalidation when source mutation has no dataset', () => {
    const dataset = fixture();
    const approved = approvePlan(reviewAll(withDraft(dataset)), 'alpha', dataset);
    const changed = setSourceActive(approved, 'unrelated-source', false);
    expect(changed.plans.alpha.approvedSignature).toBeNull();
    expect(changed.plans.alpha.fields.every(item => item.review === 'unreviewed')).toBe(true);
    expect(approved.plans.alpha.approvedSignature).not.toBeNull();
  });

  it('rejects malformed imported state and does not trust buyer-confirmed flags or fabricated token metrics', () => {
    const dataset = fixture();
    expect(restoreState({ version: 2, plans: { alpha: { approvedSignature: 'fake' } } }, dataset)).toEqual(createInitialState(dataset));
    const state = withDraft(dataset);
    const raw = JSON.parse(JSON.stringify(state));
    raw.plans.alpha.fields[0].buyerConfirmed = true;
    raw.sourceOverrides = { 'not-in-dataset': false, 'alpha-event': 'false' };
    raw.runs = [{ id: 'run', accountId: 'alpha', startedAt: '2026-11-12T10:00:00Z', elapsedMs: 120, status: 'failed', provider: 'deepseek', inputTokens: -1, outputTokens: '500', error: 'Provider unavailable' }];
    const restored = restoreState(raw, dataset);
    expect(restored.plans.alpha.fields[0].buyerConfirmed).toBe(false);
    expect(restored.sourceOverrides).toEqual({});
    expect(restored.runs[0]).not.toHaveProperty('inputTokens');
    expect(restored.runs[0]).not.toHaveProperty('outputTokens');
    expect(restored.runs[0].elapsedMs).toBe(120);
  });

  it.each(['fact', 'scenario'] as const)('rejects crafted restored core %s fields despite a valid signature and public citation', basis => {
    const dataset = fixture();
    const approved = approvePlan(reviewAll(withDraft(dataset)), 'alpha', dataset);
    const crafted = structuredClone(approved);
    const pain = crafted.plans.alpha.fields.find(item => item.id === 'pain')!;
    pain.basis = basis;
    pain.value = 'The buyer has a broken workflow and an approved budget.';
    pain.sourceIds = ['alpha-context'];
    expect(crafted.plans.alpha.approvedSignature).toBe(inputSignature('alpha', dataset, crafted));
    expect(restoreState(crafted, dataset).plans.alpha).toBeUndefined();
    expect(() => approvePlan(crafted, 'alpha', dataset)).toThrow(/Core plan fields/);
  });

  it('keeps disabled or cross-account contact profiles out of draft and brief leads', () => {
    const dataset = fixture();
    dataset.contacts.push({ id: 'lead', accountId: 'alpha', name: 'Alex Verifiable', title: 'CFO', function: 'finance', url: 'https://alpha.example/alex', linkedin: null, email: 'alex@demo.invalid', emailVerified: false, titleStatus: 'public', researchedAt: '2026-11-12', uncertainty: 'Buying authority unknown' });
    dataset.accounts[0].sourceIds.push('lead-profile');
    dataset.sources.push(source('lead-profile', 'alpha', { title: 'Alex Verifiable — professional profile', text: 'Alex Verifiable is CFO.' }));
    const initial = createInitialState(dataset);
    expect(draftPlan(rankAccounts(dataset, initial)[0], dataset, initial).fields.find(item => item.id === 'people')?.value).toContain('Alex Verifiable');
    expect(makeBrief(dataset, initial, 'daily').items[0].contact).toContain('Alex Verifiable');
    const disabled = setSourceActive(initial, 'lead-profile', false, dataset);
    expect(draftPlan(rankAccounts(dataset, disabled)[0], dataset, disabled).fields.find(item => item.id === 'people')?.value).not.toContain('Alex Verifiable');
    expect(makeBrief(dataset, disabled, 'daily').items[0].contact).toContain('No researched contact');
    dataset.sources.find(item => item.id === 'lead-profile')!.accountId = 'other-account';
    expect(draftPlan(rankAccounts(dataset, initial)[0], dataset, initial).fields.find(item => item.id === 'people')?.value).not.toContain('Alex Verifiable');
    expect(makeBrief(dataset, initial, 'daily').items[0].contact).toContain('No researched contact');
  });

  it('keeps the public snapshot brief and cites only displayed context and event excerpts', () => {
    const dataset = fixture();
    dataset.accounts[0].sourceIds.push('alpha-fund-context', 'alpha-old-event');
    dataset.accounts[0].eventIds.push('alpha-old-event');
    dataset.sources[0].text = 'Firm strategy evidence. '.repeat(120);
    dataset.sources[1].text = 'Closed Fund IX; dated fund announcement. '.repeat(120);
    dataset.sources.push(source('alpha-fund-context', 'alpha', { text: 'Published fund context. '.repeat(120) }),
      source('alpha-old-event', 'alpha', { text: 'Closed an older fund.', date: '2020-01-01' }));
    for (let i = 0; i < 12; i++) {
      const id = `contact-${i}-profile`;
      dataset.accounts[0].sourceIds.push(id);
      dataset.sources.push(source(id, 'alpha', { text: `Profile-only person ${i}. `.repeat(100) }));
    }
    const state = createInitialState(dataset);
    const snapshot = draftPlan(rankAccounts(dataset, state)[0], dataset, state).fields.find(item => item.id === 'snapshot')!;
    expect(snapshot.value.length).toBeLessThanOrEqual(1_000);
    expect(snapshot.value).toContain('Firm strategy evidence.');
    expect(snapshot.value).toContain('Published fund context.');
    expect(snapshot.value).toContain('Closed Fund IX');
    expect(snapshot.value).not.toContain('Profile-only person');
    expect(snapshot.value).not.toContain('older fund');
    expect(snapshot.sourceIds.sort()).toEqual(['alpha-context', 'alpha-event', 'alpha-fund-context']);
    const disabled = setSourceActive(state, 'alpha-fund-context', false, dataset);
    const updated = draftPlan(rankAccounts(dataset, disabled)[0], dataset, disabled).fields.find(item => item.id === 'snapshot')!;
    expect(updated.sourceIds).not.toContain('alpha-fund-context');
    expect(updated.value).not.toContain('Published fund context.');
  });

  it('starts with active legal entry leads, then operations and IR before finance, without assigning authority', () => {
    const dataset = fixture();
    const leads = [
      { id: 'a-finance', name: 'Emily Controller', title: 'Controller', function: 'finance' },
      { id: 'b-ir', name: 'Iris Relations', title: 'Head of Investor Relations', function: 'investor relations' },
      { id: 'c-operations', name: 'Omar Operations', title: 'Chief Operating Officer', function: 'operations' },
      { id: 'y-legal', name: 'Casey Counsel', title: 'General Counsel and CCO', function: 'legal / compliance' },
      { id: 'z-legal', name: 'Leslie Counsel', title: 'AGC', function: 'legal' },
    ];
    for (const lead of leads) {
      dataset.contacts.push({ ...lead, accountId: 'alpha', url: `https://alpha.example/${lead.id}`, linkedin: null, email: `${lead.id}@demo.invalid`, emailVerified: false, titleStatus: 'public', researchedAt: '2026-11-12', uncertainty: 'Authority unknown' });
      dataset.accounts[0].sourceIds.push(`${lead.id}-profile`);
      dataset.sources.push(source(`${lead.id}-profile`, 'alpha', { text: `${lead.name}: ${lead.title}.` }));
    }
    const state = createInitialState(dataset);
    const people = draftPlan(rankAccounts(dataset, state)[0], dataset, state).fields.find(item => item.id === 'people')!;
    expect(people.value.indexOf('Casey Counsel')).toBeLessThan(people.value.indexOf('Leslie Counsel'));
    expect(people.value.indexOf('Leslie Counsel')).toBeLessThan(people.value.indexOf('Omar Operations'));
    expect(people.value).not.toContain('Emily Controller');
    expect(people.value).toContain('Entry-role hypothesis');
    expect(people.basis).toBe('unknown');
    expect(makeBrief(dataset, state, 'daily').items[0].contact).toContain('Casey Counsel');
    let disabled = setSourceActive(state, 'y-legal-profile', false, dataset);
    disabled = setSourceActive(disabled, 'z-legal-profile', false, dataset);
    expect(makeBrief(dataset, disabled, 'daily').items[0].contact).toContain('Omar Operations');
    disabled = setSourceActive(disabled, 'c-operations-profile', false, dataset);
    expect(makeBrief(dataset, disabled, 'daily').items[0].contact).toContain('Iris Relations');
    disabled = setSourceActive(disabled, 'b-ir-profile', false, dataset);
    expect(makeBrief(dataset, disabled, 'daily').items[0].contact).toContain('Emily Controller');
  });
});

describe('model output boundary', () => {
  it('accepts a conditional, cited response while retaining a sourced snapshot and human review', () => {
    const dataset = fixture(), state = createInitialState(dataset), ranked = rankAccounts(dataset, state)[0];
    const plan = validateModelPlan(model(), ranked, dataset, state);
    expect(plan.generatedBy).toBe('deepseek');
    expect(plan.fields.find(item => item.id === 'snapshot')?.basis).toBe('fact');
    expect(plan.fields.find(item => item.id === 'pain')).toMatchObject({ basis: 'unknown', buyerConfirmed: false });
    expect(plan.fields.every(item => item.review === 'unreviewed')).toBe(true);
    expect(plan.approvedSignature).toBeNull();
  });

  it('rejects wrong account, factual private claims, missing fields and duplicate IDs', () => {
    const dataset = fixture(), state = createInitialState(dataset), ranked = rankAccounts(dataset, state)[0];
    const cases: unknown[] = [
      { ...model(), account_id: 'other' },
      { ...model(), fields: model().fields.map(item => item.id === 'pain' ? { ...item, basis: 'fact', value: 'Their workflow is broken.' } : item) },
      { ...model(), fields: model().fields.filter(item => item.id !== 'people') },
      { ...model(), fields: [...model().fields, model().fields[0]] },
    ];
    for (const value of cases) expect(() => validateModelPlan(value, ranked, dataset, state)).toThrow();
  });

  it('rejects missing, disabled and cross-account references', () => {
    const dataset = fixture(), initial = createInitialState(dataset);
    dataset.sources.push(source('other-evidence', 'other'));
    for (const id of ['missing', 'other-evidence']) {
      const raw = model(); raw.fields[0].source_ids = [id];
      expect(() => validateModelPlan(raw, rankAccounts(dataset, initial)[0], dataset, initial)).toThrow(/evidence/);
    }
    const disabled = setSourceActive(initial, 'alpha-event', false, dataset);
    expect(() => validateModelPlan(model(), rankAccounts(dataset, disabled)[0], dataset, disabled)).toThrow(/evidence/);
  });

  it('rejects uncited or unconditional hypotheses and demo or instruction wording', () => {
    const dataset = fixture(), state = createInitialState(dataset), ranked = rankAccounts(dataset, state)[0];
    const uncited = model(); uncited.fields[0].source_ids = [];
    expect(() => validateModelPlan(uncited, ranked, dataset, state)).toThrow(/active evidence/);
    const assertion = model(); assertion.fields[0].value = 'They need a new obligation system this quarter.';
    expect(() => validateModelPlan(assertion, ranked, dataset, state)).toThrow(/conditional/);
    dataset.sources[1].kind = 'scenario'; dataset.sources[1].url = null;
    // Account-record evidence is usable as-is; the app labels example data on screen, not in the text.
    expect(validateModelPlan(model(), ranked, dataset, state).generatedBy).toBe('deepseek');
    for (const leak of ['Hypothesis for this fictional scenario: ask about it.', 'Hypothesis: No demo hold applies; ask about it.', 'Hypothesis: as a net_new account, ask about it.']) {
      const raw = model(); raw.fields[0].value = leak;
      expect(() => validateModelPlan(raw, ranked, dataset, state)).toThrow(/leaked/);
    }
    const listLeak = model(); listLeak.questions = ['What does the illustrative escalation involve?'];
    expect(() => validateModelPlan(listLeak, ranked, dataset, state)).toThrow(/leaked/);
  });

  it('replaces held-customer AI expansion actions with the fixed hold resolution', () => {
    const dataset = fixture();
    dataset.accounts[0].motion = 'customer_hold';
    dataset.accounts[0].holdReason = 'Open service escalation';
    const state = createInitialState(dataset), ranked = rankAccounts(dataset, state)[0];
    const raw = model();
    raw.fields.find(item => item.id === 'next_action')!.value = 'Hypothesis: propose an immediate expansion to additional funds.';
    raw.actions = ['Propose an expansion to the account now.'];
    const plan = validateModelPlan(raw, ranked, dataset, state);
    expect(plan.actions).toEqual([ranked.nextAction]);
    expect(plan.actions.join(' ')).toContain('account owner');
    expect(plan.actions.join(' ')).toContain('before raising expansion');
    expect(plan.actions.join(' ')).not.toContain('account now');
    expect(plan.fields.find(item => item.id === 'next_action')).toMatchObject({ basis: 'unknown', sourceIds: [], buyerConfirmed: false });
    expect(plan.fields.find(item => item.id === 'next_action')?.value).toBe(`Unknown: whether the customer is ready to talk about more scope. ${ranked.nextAction}`);
    expect(JSON.stringify(plan.fields.filter(item => item.id !== 'demo_motion'))).not.toMatch(/fictional|illustrative/i);
    expect(plan.fields.find(item => item.id === 'next_action')?.value).not.toContain('immediate expansion');
  });
});

describe('brief truthfulness and prepared-data regression', () => {
  it('shows no invented change before a baseline, then compares only saved displayed records', () => {
    const dataset = fixture(), state = createInitialState(dataset);
    const first = makeBrief(dataset, state, 'daily');
    expect(first.changeNote).toContain('No previous');
    const saved = { ...state, previousBrief: first };
    expect(makeBrief(dataset, saved, 'weekly').changeNote).toContain('No changes');
    const disabled = setSourceActive(saved, 'alpha-event', false, dataset);
    expect(makeBrief(dataset, disabled, 'daily').changeNote).toContain('1 changed');
  });

  it('caps eligible net-new records at five while retaining separate customer exceptions', () => {
    const dataset = fixture();
    for (let i = 0; i < 7; i++) {
      const id = `firm${i}`;
      dataset.accounts.push(account(id)); dataset.sources.push(source(`${id}-context`, id));
    }
    const state = createInitialState(dataset);
    expect(makeBrief(dataset, state, 'weekly').items).toHaveLength(5);
    expect(makeBrief(dataset, state, 'weekly').exceptions).toHaveLength(0);
  });

  it('makes Advent the only public fresh P1 and removes that priority when its event is disabled', () => {
    const dataset = prepared as unknown as Dataset, state = createInitialState(dataset);
    const queue = rankAccounts(dataset, state);
    expect(queue.filter(item => item.priority === 'P1').map(item => item.id)).toEqual(['advent_international']);
    expect(queue.find(item => item.id === 'francisco_partners')?.temperature).toBe('Unknown');
    expect(queue.every(item => item.fit !== 'High')).toBe(true);
    const disabled = setSourceActive(state, 'advent_international-event', false, dataset);
    expect(rankAccounts(dataset, disabled).find(item => item.id === 'advent_international')).toMatchObject({ priority: 'P2', temperature: 'Unknown' });
    expect(dataset.accounts).toHaveLength(11);
    expect(dataset.contacts).toHaveLength(104);
  });
});

describe('propensity score (0–10)', () => {
  it('adds four bounded drivers and explains each one', () => {
    const dataset = fixture();
    const score = rankAccounts(dataset, createInitialState(dataset))[0].score!;
    expect(score.max).toBe(10);
    expect(score.drivers.map(driver => driver.id)).toEqual(['timing', 'fit', 'reach', 'evidence']);
    expect(score.drivers.map(driver => driver.max).reduce((a, b) => a + b, 0)).toBe(10);
    for (const driver of score.drivers) {
      expect(driver.points).toBeGreaterThanOrEqual(0);
      expect(driver.points).toBeLessThanOrEqual(driver.max);
      expect(driver.detail.length).toBeGreaterThan(0);
    }
    expect(score.total).toBeCloseTo(score.drivers.reduce((sum, driver) => sum + driver.points, 0), 5);
    // 16 days before the research date: 4 × (1 − 16/365) ≈ 3.8
    expect(score.drivers[0].points).toBe(3.8);
  });

  it('scores buyer access by buying role: named and sourced holder is full credit, role-only is half', () => {
    const dataset = prepared as unknown as Dataset, state = createInitialState(dataset);
    const reach = (id: string) => rankAccounts(dataset, state).find(item => item.id === id)!.score!.drivers.find(driver => driver.id === 'reach')!;
    // Advent: named CCO, CFO and IR co-head, each with an official source page.
    expect(reach('advent_international').points).toBe(2);
    expect(reach('advent_international').detail).toContain('Champion (GC or CCO): Heather Zuzenak, named and sourced (1)');
    // GTCR: the legal chief's role needs re-confirming, so the champion role earns half.
    expect(reach('gtcr').points).toBe(1.5);
    expect(reach('gtcr').detail).toContain('Jeff Wright, role to re-confirm (0.5)');
    // Audax: IR team is known but no head is named.
    expect(reach('audax').points).toBe(1.75);
    expect(reach('audax').detail).toContain('IR lead: role identified, holder not named (0.25)');
    // A general counsel of a sub-unit is not preferred over the firm's chief legal officer.
    expect(reach('vista_equity_partners').detail).toContain('Christina Lema');
    const none = buyerAccess([]);
    expect(none.map(item => item.points)).toEqual([0, 0, 0]);
  });

  it('never lets seller activity raise the score: the simulated activity record changes nothing', () => {
    const dataset = prepared as unknown as Dataset, state = createInitialState(dataset);
    const score = (s: typeof state) => rankAccounts(dataset, s).find(item => item.id === 'advent_international')!.score!;
    expect(dataset.sources.find(item => item.id === 'SIM-ACT-001')?.kind).toBe('scenario');
    expect(score(setSourceActive(state, 'SIM-ACT-001', false, dataset))).toEqual(score(state));
    expect(score(state).total).toBe(9.1);
    expect(score(state).drivers[0].detail).toContain('Credit fades evenly to zero over 365 days');
  });

  it("checks the AI email against this account's sourced contacts", () => {
    const dataset = prepared as unknown as Dataset, state = createInitialState(dataset);
    const ranked = rankAccounts(dataset, state).find(item => item.id === 'advent_international')!;
    const base = () => ({ account_id: 'advent_international',
      fields: ['goals', 'pain', 'people', 'strategy', 'next_action'].map(id => ({ id, label: id, basis: 'hypothesis',
        source_ids: ['advent_international-context'], value: 'Hypothesis: ask how side letter obligations are tracked.' })),
      questions: ['How are side letter obligations tracked today?'], actions: ['Prepare for the meeting.'],
      email: { contact_id: 'CT-2f153a16442e-profile', subject: 'Pre-read', body: 'Hi Heather, a short pre-read before we meet. Anything to add?' } });
    expect(validateModelPlan(base(), ranked, dataset, state).email).toEqual(
      { contactId: 'CT-2f153a16442e', subject: 'Pre-read', body: 'Hi Heather,\n\nA short pre-read before we meet. Anything to add?' });
    const other = base(); other.email.contact_id = 'CT-9958bb32b128-profile'; // an HGGC contact
    expect(() => validateModelPlan(other, ranked, dataset, state)).toThrow(/outside this account/);
    const wrongName = base(); wrongName.email.body = 'Hi Rachel, a short pre-read.';
    expect(() => validateModelPlan(wrongName, ranked, dataset, state)).toThrow(/greet/);
    // The exact phrase that reached a seller on 2026-11-15.
    const leak = base(); leak.email.body = 'Hi Heather, can you describe the illustrative service escalation in this fictional scenario?';
    expect(() => validateModelPlan(leak, ranked, dataset, state)).toThrow(/leaked/);
    const vocabulary = base(); vocabulary.questions = ['How do you track investor commitments today?'];
    expect(() => validateModelPlan(vocabulary, ranked, dataset, state)).toThrow(/leaked/);
    const demo = base(); demo.actions = ['Schedule a demo with the General Counsel.'];
    expect(validateModelPlan(demo, ranked, dataset, state).actions).toEqual(['Schedule a demo with the General Counsel.']);
  });

  it('rewrites "investor obligations" to the LP wording in everything a seller reads', () => {
    const dataset = prepared as unknown as Dataset, state = createInitialState(dataset);
    const ranked = rankAccounts(dataset, state).find(item => item.id === 'advent_international')!;
    const plan = validateModelPlan({ account_id: 'advent_international',
      fields: ['goals', 'pain', 'people', 'strategy', 'next_action'].map(id => ({ id, label: 'Investor obligations', basis: 'hypothesis',
        source_ids: ['advent_international-context'], value: 'Hypothesis: ask how investor obligations and each investor-specific obligation are tracked.' })),
      questions: ['Who owns investor-obligation tracking today?'], actions: ['Ask Investor Relations who tracks investor obligations.'],
      email: { contact_id: 'CT-2f153a16442e-profile', subject: 'Investor obligations', body: 'Hi Heather, how are investor obligations tracked today?' } },
      ranked, dataset, state);
    const text = JSON.stringify([plan.fields.filter(item => item.id !== 'snapshot' && item.id !== 'demo_motion'), plan.questions, plan.actions, plan.email]);
    expect(text).not.toMatch(/investor[- ]obligation|investor-specific/i);
    expect(plan.questions).toEqual(['Who owns LP-obligation tracking today?']);
    expect(plan.email).toMatchObject({ subject: 'LP obligations', body: 'Hi Heather,\n\nHow are LP obligations tracked today?' });
    // The department name is left alone.
    expect(plan.actions).toEqual(['Ask Investor Relations who tracks LP obligations.']);
  });

  it('rejects filler wording and replaces em dashes with plain punctuation', () => {
    const dataset = prepared as unknown as Dataset, state = createInitialState(dataset);
    const ranked = rankAccounts(dataset, state).find(item => item.id === 'advent_international')!;
    const base = () => ({ account_id: 'advent_international',
      fields: ['goals', 'pain', 'people', 'strategy', 'next_action'].map(id => ({ id, label: id, basis: 'hypothesis',
        source_ids: ['advent_international-context'], value: 'Hypothesis: ask how side letter obligations are tracked.' })),
      questions: ['How are side letter obligations tracked today — in a spreadsheet or a system?'], actions: ['Prepare for the meeting.'],
      email: { contact_id: 'CT-2f153a16442e-profile', subject: 'Pre-read', body: 'Hi Heather, thanks for the call — a short pre-read follows. Anything to add?' } });
    const plan = validateModelPlan(base(), ranked, dataset, state);
    expect(plan.questions).toEqual(['How are side letter obligations tracked today, in a spreadsheet or a system?']);
    expect(plan.email!.body).toBe('Hi Heather,\n\nThanks for the call, a short pre-read follows. Anything to add?');
    for (const phrase of ['I imagine tracking gets harder each fund.', 'I wanted to reach out directly.', 'A seamless, robust way to track them.', 'Could a bespoke report help?', 'I am curious how you track them.', 'I’m curious how you track them.']) {
      const filler = base(); filler.email.body = `Hi Heather, ${phrase}`;
      expect(() => validateModelPlan(filler, ranked, dataset, state)).toThrow(/filler/);
    }
    const finance = base(); finance.questions = ['How does the leveraged buyout fund track its side letter obligations?'];
    expect(validateModelPlan(finance, ranked, dataset, state).questions).toHaveLength(1);
  });

  it('scores Battery Ventures from its public fund close and named buying roles, behind Advent and Francisco', () => {
    const dataset = prepared as unknown as Dataset, state = createInitialState(dataset);
    const queue = rankAccounts(dataset, state).filter(item => item.score);
    expect(queue.slice(0, 3).map(item => item.id)).toEqual(['advent_international', 'francisco_partners', 'battery_ventures']);
    const battery = queue.find(item => item.id === 'battery_ventures')!;
    expect(battery.priority).toBe('P2');
    expect(battery.score!.total).toBe(7.1);
    const driver = (id: string) => battery.score!.drivers.find(item => item.id === id)!;
    expect(driver('timing').detail).toContain('Fund event Feb 18, 2026 · 267 days before research date');
    expect(driver('reach').detail).toContain('Champion (GC or CCO): Lizette Perez-Deisboeck, named and sourced (1)');
    // "Infrastructure software" is a sector, not an infrastructure strategy.
    expect(driver('fit').detail).toContain('3 strategies (buyout / private equity, growth, venture / early stage)');
    // Every Battery record is a public source with a link; nothing simulated.
    const sources = dataset.sources.filter(item => item.accountId === 'battery_ventures');
    expect(sources).toHaveLength(11);
    expect(sources.every(item => item.kind === 'public' && /^https:\/\/www\.battery\.com\//.test(item.url ?? ''))).toBe(true);
  });

  it('drops when the dated trigger is excluded, and timing goes to zero', () => {
    const dataset = fixture();
    const initial = createInitialState(dataset);
    const before = rankAccounts(dataset, initial)[0].score!;
    const after = rankAccounts(dataset, setSourceActive(initial, 'alpha-event', false, dataset))[0].score!;
    expect(after.total).toBeLessThan(before.total);
    expect(after.drivers[0].points).toBe(0);
    expect(after.drivers[0].detail).toContain('No relevant');
  });

  it('gives no timing credit for acquisition publicity or events older than a year', () => {
    const acquisition = fixture();
    acquisition.sources[1] = { ...acquisition.sources[1], text: 'Fund VIII closed the acquisition of a software business.' };
    expect(rankAccounts(acquisition, createInitialState(acquisition))[0].score!.drivers[0].points).toBe(0);
    const old = fixture();
    old.sources[1] = { ...old.sources[1], date: '2025-06-01' };
    const timing = rankAccounts(old, createInitialState(old))[0].score!.drivers[0];
    expect(timing.points).toBe(0);
    expect(timing.detail).toContain('over a year old');
  });

  it('does not score customer scenarios', () => {
    const dataset = fixture();
    dataset.accounts[0] = { ...dataset.accounts[0], motion: 'customer_hold', holdReason: 'Fictional hold' };
    expect(rankAccounts(dataset, createInitialState(dataset))[0].score).toBeNull();
  });

  it('orders same-priority accounts by score instead of name', () => {
    const dataset = fixture();
    dataset.accounts.push(account('aaa', { eventIds: [], sourceIds: ['aaa-context'] }));
    dataset.accounts.push(account('zeta', { eventIds: ['zeta-event'], sourceIds: ['zeta-context', 'zeta-event'] }));
    dataset.sources.push(source('aaa-context', 'aaa'), source('zeta-context', 'zeta'),
      source('zeta-event', 'zeta', { title: 'Fund close', text: 'Closed Fund III at $1 billion.', date: '2026-03-01' }));
    const p2 = rankAccounts(dataset, createInitialState(dataset)).filter(item => item.priority === 'P2').map(item => item.id);
    expect(p2).toEqual(['zeta', 'aaa']);
  });

  it('scores the prepared sample so the fundraise moment is visible', () => {
    const dataset = prepared as Dataset;
    const initial = createInitialState(dataset);
    const advent = () => (state: WorkspaceState) => rankAccounts(dataset, state).find(item => item.id === 'advent_international')!;
    expect(advent()(initial)).toMatchObject({ priority: 'P1' });
    expect(advent()(initial).score!.total).toBeGreaterThan(8.5);
    const off = advent()(setSourceActive(initial, 'advent_international-event', false, dataset));
    expect(off.priority).toBe('P2');
    expect(off.score!.total).toBeLessThan(5);
  });
});
