"""Deterministic seller-scenario simulations for the Pearl workspace.

Drives the real app in Chromium and records clicks, timing and pass/fail checks
for each scenario. The model is never called: /api/status is forced to 404, so
plan drafting uses the saved real run (Advent) or the prepared draft. One
scenario forces a model failure to check the fallback path; another streams a
scripted draft through /api/draft to check the live view and the one-time redraft.

Usage:
  python scripts/simulate_sellers.py --url http://127.0.0.1:8767/ --out docs/simulations
"""
from __future__ import annotations
import argparse, json, re, time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

SCENARIOS = []
def scenario(name, persona, viewport=(1440, 900)):
    def wrap(fn):
        SCENARIOS.append((name, persona, viewport, fn)); return fn
    return wrap


class Run:
    def __init__(self, page: Page, shots: Path, key: str):
        self.page, self.shots, self.key = page, shots, key
        self.clicks, self.checks, self.steps, self.errors = 0, [], [], []
        self.t0 = time.perf_counter(); self.marks = {}
        page.on('pageerror', lambda e: self.errors.append(str(e)))
        page.on('console', lambda m: self.errors.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)

    def click(self, selector, label=None, nth=0):
        loc = self.page.locator(selector).nth(nth)
        loc.wait_for(state='visible', timeout=15000); loc.click(); self.clicks += 1
        self.steps.append(label or selector); self.page.wait_for_timeout(120)

    def fill(self, selector, text, label):
        self.page.fill(selector, text); self.steps.append(label)

    def check(self, label, ok, detail=''):
        self.checks.append({'check': label, 'pass': bool(ok), 'detail': str(detail)[:300]})

    def mark(self, name):
        self.marks[name] = {'clicks': self.clicks, 'ms': round((time.perf_counter() - self.t0) * 1000)}

    def text(self, selector='body'):
        return self.page.locator(selector).first.inner_text()

    def shot(self, name):
        path = self.shots / f'{self.key}_{name}.png'; self.page.screenshot(path=str(path)); return path.name

    def no_overflow(self, label):
        width = self.page.evaluate('document.documentElement.scrollWidth'); vw = self.page.viewport_size['width']
        self.check(f'No horizontal scroll: {label}', width <= vw, f'scrollWidth {width} vs viewport {vw}')


def go_focus(r: Run):
    r.click('.ai-sidebar [data-nav="focus"]', 'Open My focus'); r.page.wait_for_timeout(500)


def build_and_approve(r: Run, account='advent', edit=None):
    r.click(f'#ai-stage [data-account="{account}"]', f'Open {account}')
    r.click('#ai-stage [data-build-plan]', 'Build account plan')
    r.page.locator('#ai-plan-action').wait_for(state='visible', timeout=40000)
    if edit: r.fill('#ai-plan-action', edit, 'Edit next action')
    r.click('#ai-approve-plan', 'Approve plan')


EDIT = 'Confirm who owns the obligation-tracking process across GPE XI and the new mid-market strategy.'


@scenario('monday', 'Seller on a normal Monday: rank, plan, approve, brief')
def monday(r: Run):
    go_focus(r); body = r.text('#ai-stage')
    r.check('Top five starts with Advent 9.1 P1', 'Advent International' in body and '9.1' in body)
    r.check('Time-back estimate visible on My focus', '4.7–8.4 h' in body, body[:200])
    build_and_approve(r, edit=EDIT); r.mark('first_approved_plan')
    r.check('Plan approved', 'approved' in r.text('#ai-toast').lower() or 'Approach approved' in r.text())
    go_focus(r); r.click('#ai-stage [data-brief-kind="weekly"]', 'Weekly brief')
    r.click('#ai-compose-brief', 'Prepare brief'); r.page.locator('#ai-save-brief').wait_for(timeout=5000)
    brief = r.text('.ai-modal'); r.shot('weekly_brief')
    r.check('Seller edit carried into the weekly brief verbatim', EDIT in brief)
    r.check('Unreviewed accounts labeled Suggested', 'Suggested' in brief)
    first = r.page.locator('.ai-modal .ai-weekplan > li').first.inner_text()
    r.check('The approved Advent move is not marked Suggested', EDIT in first and 'Suggested' not in first, first[:300])
    r.click('#ai-save-brief', 'Save brief'); r.mark('brief_saved')


@scenario('new_seller', 'New seller inheriting the book')
def new_seller(r: Run):
    go_focus(r); r.click('#ai-stage [data-catchup]', 'Catch me up')
    r.click('[data-catch-run]', 'Prepare handover brief'); r.page.locator('.ai-weekplan').wait_for(timeout=5000)
    r.mark('book_understood'); text = r.text('.ai-modal'); r.shot('handover')
    start = text.split('Your priority accounts')[1].split('Customer priorities')[0]
    order = [start.find(n) for n in ('Advent International', 'Francisco Partners', 'Battery Ventures')]
    r.check('Your priority accounts = Advent, Francisco, Battery Ventures in score order', all(i >= 0 for i in order) and order == sorted(order), order)
    r.check('Churn risk surfaced under Customer priorities: HGGC retention play', 'Customer priorities' in text and 'HGGC' in text and 'Retention play' in text)
    r.check('Expansion surfaced: TA Associates expansion opportunity', 'TA Associates' in text and 'Expansion opportunity' in text)
    plan = r.text('.ai-modal .ai-weekplan'); rows = r.page.locator('.ai-modal .ai-weekplan > li').count()
    r.check('Plan for the week covers all five accounts at once, not one per day', rows == 5 and 'Plan for the week' in text and 'Start with these priority accounts' in text and not re.search(r'(?im)^\s*(mon|tue|wed|thu|fri)\s*$', text), (rows, plan[:200]))
    r.check('Each account names its people with titles', all(x in plan for x in ('Heather Zuzenak, Chief Compliance Officer', 'Steve Eisner, Partner, General Counsel', 'Lizette Perez-Deisboeck, General Counsel and Chief Compliance Officer', 'Daniel Weintraub, Chief Legal Officer', 'David A. Smolen, Managing Director')), plan[:700])
    r.click('.ai-weekplan [data-account="advent"]', 'Plan: open Advent')
    r.check('Plan link lands on Advent record', 'Advent International' in r.text('#ai-breadcrumb'))
    r.click('#ai-stage [data-build-plan]', 'Build account plan')
    r.page.locator('#ai-plan-action').wait_for(state='visible', timeout=40000)
    r.click('#ai-approve-plan', 'Approve plan'); r.mark('first_approved_plan')
    go_focus(r); r.click('#ai-stage [data-catchup]', 'Catch me up')
    r.click('[data-catch-run]', 'Prepare handover again'); r.page.locator('.ai-weekplan').wait_for(timeout=5000)
    r.click('.ai-modal .ai-punchlist [data-account="hggc"]', 'Customer priorities: open HGGC')
    r.click('#ai-cs-review', 'Start retention play'); r.mark('retention_play')
    r.click('.ai-sidebar [data-nav="tasks"]', 'My tasks'); tasks = r.text('#ai-stage')
    r.check('Retention play task owned by the account team', 'Retention play' in tasks and 'Account team' in tasks, tasks[:300])


@scenario('back_from_leave', 'Seller back after 3 weeks away, nothing left open')
def back_from_leave(r: Run):
    go_focus(r); r.click('#ai-stage [data-catchup]', 'Catch me up'); r.click('[data-catch-kind="return"]', 'Back from leave')
    r.click('[data-catch-run]', 'Prepare return brief'); r.page.locator('.ai-changelist').wait_for(timeout=5000)
    r.mark('changes_understood'); t3 = r.text('.ai-modal'); r.shot('return_3wk')
    r.check('3 weeks: 5 changes across 4 accounts', '5 changes across 4 accounts' in t3, t3[:160])
    r.check('Advent event explains the move: score 4.0 → 9.1, now P1', '4.0 → 9.1' in t3 and 'Now P1' in t3)
    r.check('New GTCR contacts listed', t3.count('New researched contact') == 2)
    r.check('HGGC usage drop listed with a retention play', 'Weekly users 22 → 11' in t3 and 'retention play' in t3.lower())
    r.click('[data-leave-weeks="2"]', '2 weeks away'); t2 = r.text('.ai-modal')
    r.check('2 weeks: Oct 27 event correctly drops out (4 changes)', '4 changes' in t2 and 'Advent International' not in t2.split('While you were out')[1].split('Your work')[0])
    r.click('[data-leave-weeks="4"]', '4 weeks away'); t4 = r.text('.ai-modal')
    r.check('4 weeks: same 5 changes (no other dated events in window)', '5 changes' in t4)
    r.check('Nothing open on a clean workspace', 'Nothing open' in t4)
    r.click('.ai-dayplan [data-account="advent"]', 'Pick up: open Advent')
    r.check('Pick-up link lands on Advent record', 'Advent International' in r.text('#ai-breadcrumb'))


@scenario('back_from_leave_stale', 'Seller back from leave whose approved plan was invalidated while away')
def back_stale(r: Run):
    go_focus(r); build_and_approve(r, edit=EDIT)
    # While the seller is away, the dated event is withdrawn (excluded as evidence).
    r.click('.ai-sidebar [data-account="advent"]', 'Open Advent record')
    r.click('#ai-stage [data-modal="research"]', 'Change inputs')
    r.page.locator('#ai-event-toggle').uncheck(force=True); r.clicks += 1; r.steps.append('Exclude the dated event'); r.page.wait_for_timeout(300)
    r.check('Excluding the event drops Advent to 4.0 / P2', 'Score 9.1 → 4.0, P1 → P2' in r.text('#ai-toast'), r.text('#ai-toast'))
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    go_focus(r); r.click('#ai-stage [data-catchup]', 'Catch me up'); r.click('[data-catch-kind="return"]', 'Back from leave')
    r.click('[data-catch-run]', 'Prepare return brief'); r.page.locator('.ai-changelist').wait_for(timeout=5000)
    t = r.text('.ai-modal'); r.shot('return_stale')
    r.check('Excluded event is labeled, not presented as a reason to call', 'excluded by you' in t and 'Not buying intent' in t, t[:400])
    r.check('Invalidated plan surfaces as open work', 'Your open work' in t and ('needs your review' in t or 'waiting for your approval' in t))


@scenario('ai_failure', 'Live model fails mid-demo')
def ai_failure(r: Run):
    go_focus(r); r.click('#ai-stage [data-account="advent"]', 'Open Advent')
    r.click('#ai-stage [data-build-plan]', 'Build account plan')
    r.page.locator('#ai-plan-action').wait_for(state='visible', timeout=40000)
    body = r.text('#ai-stage'); r.shot('ai_failure')
    r.check('Failure is stated, prepared draft shown, work kept', ('failed' in body.lower() or 'prepared draft' in body.lower()) and r.page.input_value('#ai-plan-action').strip() != '', body[:300])


@scenario('stress', 'Rapid and hostile input')
def stress(r: Run):
    go_focus(r)
    r.click('#ai-stage [data-catchup]', 'Catch me up')
    for _ in range(4):
        r.page.locator('[data-catch-run]').first.click(); r.clicks += 1
    r.page.wait_for_timeout(1200)
    r.check('Repeated Prepare clicks leave one brief, no errors', r.page.locator('.ai-modal').count() == 1 and r.page.locator('.ai-weekplan').count() == 1)
    r.click('[data-catch-run]', 'Prepare again'); r.page.keyboard.press('Escape'); r.page.wait_for_timeout(1000)
    r.check('Closing mid-load does not reopen the dialog', r.page.locator('.ai-modal').count() == 0)
    r.click('#ai-stage [data-account="advent"]', 'Open Advent')
    for i in range(10):
        r.page.evaluate("""() => { const ev = window.AccountIntelEngine.eventSource('advent'); window.AccountIntelEngine.setSource(ev.id, %s); }""" % ('false' if i % 2 == 0 else 'true'))
    score = r.page.evaluate("window.AccountIntelEngine.score('advent').total")
    r.check('10 event toggles return to the same score (9.1)', abs(score - 9.1) < 0.05, score)
    r.click('.ai-sidebar [data-nav="focus"]', 'My focus'); r.click('[data-open-value]', 'Time-back estimate')
    r.check('Time-back breakdown opens', 'By hand' in r.text('.ai-modal') and '4.7–8.4 h' in r.text('.ai-modal'))
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.check('Escape closes dialogs', r.page.locator('.ai-modal').count() == 0)


@scenario('mobile', 'Seller on a phone (390 px)', viewport=(390, 844))
def mobile(r: Run):
    go_focus(r); r.no_overflow('My focus'); r.shot('focus')
    r.click('[data-open-value]', 'Time-back estimate'); r.no_overflow('time-back dialog'); r.shot('value'); r.page.keyboard.press('Escape')
    r.click('#ai-stage [data-catchup]', 'Catch me up'); r.click('[data-catch-run]', 'Prepare'); r.page.locator('.ai-weekplan').wait_for(timeout=5000)
    r.no_overflow('handover brief'); r.shot('handover')
    r.click('[data-catch-kind="return"]', 'Back from leave'); r.click('[data-catch-run]', 'Prepare'); r.page.locator('.ai-changelist').wait_for(timeout=5000)
    r.no_overflow('return brief'); r.shot('return'); r.page.keyboard.press('Escape')


@scenario('no_storage', 'Browser storage blocked (private window / locked-down laptop)')
def no_storage(r: Run):
    go_focus(r); r.click('#ai-stage [data-catchup]', 'Catch me up'); r.click('[data-catch-run]', 'Prepare')
    r.page.locator('.ai-weekplan').wait_for(timeout=5000)
    r.check('Catch-up works without storage', 'Your priority accounts' in r.text('.ai-modal'))


BANNED = ['pilot', 'build versus buy', 'build vs buy', 'baseline', 'modeled', 'assumption', 'documented',
          'propensity', 'intervention', 'recovery', 'hack day', 'interview', 'revops', 'protect the base', 'purchase prediction',
          'fit to research', 'timing unconfirmed', 'about this workspace', 'fictional', 'illustrative', 'demo hold',
          'investor obligation', 'investor-obligation', 'investor commitment', 'fund obligation', 'first five days', 'seven clear moves', 'week in focus',
          'blank crm', 'starting from zero', 'in two minutes', 'seamless', 'leverage', 'unlock', 'empower', 'robust', 'streamline', 'delve',
          'game-chang', 'cutting-edge', 'supercharge', 'effortless', 'holistic', 'actionable', 'linked firm context', '/100']
_PRIVATE = Path(__file__).with_name('banned_private.txt')  # optional, untracked: extra names to keep off every screen
if _PRIVATE.exists():
    BANNED += [w.strip().lower() for w in _PRIVATE.read_text(encoding='utf-8').splitlines() if w.strip()]


@scenario('seller_voice', 'Every screen reads as a seller tool: no vendor name, no RevOps or analyst voice')
def seller_voice(r: Run):
    seen = []
    for nav in ('focus', 'accounts', 'tasks', 'briefs'):
        r.click(f'.ai-sidebar [data-nav="{nav}"]', f'Open {nav}'); r.page.wait_for_timeout(300); seen.append(r.text('body'))
    r.click('.ai-sidebar [data-nav="accounts"]', 'Open Accounts'); r.page.wait_for_timeout(300)
    rows = r.page.locator('#ai-stage .ai-queuerow')
    names = [rows.nth(i).locator('strong').first.inner_text() for i in range(rows.count())]
    scores = r.page.evaluate("""() => [...document.querySelectorAll('#ai-stage .ai-queuerow')].map(x => { const s = x.querySelector('.ai-score'); return s ? parseFloat(s.textContent) : null; })""")
    net = [s for s in scores if s is not None]
    r.check('Accounts list ranks net new by score, customers last', net == sorted(net, reverse=True) and names[-2:] == ['TA Associates', 'HGGC'] and names[0] == 'Advent International', list(zip(names, scores)))
    acct = r.text('#ai-stage')
    r.check('Customers carry customer tags, not prospect tags', 'Customer · Retention play' in acct and 'Customer · Expansion opportunity' in acct, acct[-400:])
    for a in ('advent', 'francisco', 'battery', 'audax', 'ta', 'hggc'):
        r.click(f'#ai-stage [data-account="{a}"]', f'Open {a}'); r.page.wait_for_timeout(300)
        for tab in ('overview', 'people', 'activity', 'plan'):
            loc = r.page.locator(f'#ai-stage [data-tab="{tab}"]')
            if loc.count():
                loc.first.click(); r.page.wait_for_timeout(150); seen.append(r.text('#ai-stage'))
        r.click('.ai-sidebar [data-nav="accounts"]', 'Back to Accounts'); r.page.wait_for_timeout(200)
    go_focus(r); r.click('[data-open-value]', 'Time back'); seen.append(r.text('.ai-modal')); r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.click('#ai-stage [data-catchup]', 'Catch me up'); r.click('[data-catch-run]', 'Prepare'); r.page.locator('.ai-weekplan').wait_for(timeout=5000); seen.append(r.text('.ai-modal'))
    r.click('[data-catch-kind="return"]', 'Back from leave'); r.click('[data-catch-run]', 'Prepare'); r.page.locator('.ai-changelist').wait_for(timeout=5000); seen.append(r.text('.ai-modal'))
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.click('.ai-sidebar [data-modal="seller-guide"]', 'Seller Q&A')
    for d in r.page.locator('.ai-faq details').all():
        d.evaluate('e => e.open = true')
    seen.append(r.text('.ai-modal'))
    qa = r.text('.ai-modal')
    r.check('Data disclosure answers the real-data question; no demo badge', 'Is this real customer data?' in qa and 'Preqin' in qa and 'Demo workspace' not in r.text('body'), qa[-500:])
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.click('.ai-sidebar [data-tour-start]', 'Tour')
    for i in range(10):
        r.page.locator('#ai-tour h2').wait_for(timeout=5000); seen.append(r.text('#ai-tour'))
        r.click('[data-tour-next]', 'Tour next')
    blob = ' '.join(seen).lower()
    hits = [w for w in BANNED if w in blob]
    r.check('No vendor name, RevOps or analyst phrases on any screen', not hits, hits)

ADVENT_PLAN = {
    'account_id': 'advent_international',
    'fields': [
        {'id': 'goals', 'label': 'Fund complex goals', 'basis': 'hypothesis', 'source_ids': ['advent_international-event'],
         'value': 'Hypothesis: With a new fundraise across two strategies, Advent may want one view of investor obligations across funds. Validate with the buyer.'},
        {'id': 'pain', 'label': 'Pain to confirm', 'basis': 'unknown', 'source_ids': [],
         'value': 'Unknown: no public source shows how Advent tracks side letter obligations today.'},
        {'id': 'people', 'label': 'Who to talk to', 'basis': 'hypothesis', 'source_ids': ['advent_international-context'],
         'value': 'Hypothesis: Compliance or legal leadership may own investor obligations; confirm the owner first.'},
        {'id': 'strategy', 'label': 'Angle', 'basis': 'hypothesis', 'source_ids': ['advent_international-event'],
         'value': 'Hypothesis: Lead with the fundraise as context and ask how commitments are tracked across funds.'},
        {'id': 'next_action', 'label': 'Seller next action', 'basis': 'hypothesis', 'source_ids': ['advent_international-context'],
         'value': 'Hypothesis: Prepare discovery about the obligation workflow and confirm the owner before proposing a solution.'},
    ],
    'questions': ['How do you track side letter obligations across the new funds today?'],
    'actions': ['Review the fundraise and prepare two discovery questions.'],
    'email': {'contact_id': 'CT-2f153a16442e-profile', 'subject': 'Side letters across the new funds',
              'body': 'Hi Heather,\n\nI saw Advent announced its fundraise across GPE XI and the new mid-market strategy in October. How are side letter obligations from the new funds tracked today, and who owns them?\n\nBest,\nAlex'},
}


def sse_body(plan, reject=False):
    raw = json.dumps({k: v for k, v in plan.items()})
    frames = ['event: start\ndata: ' + json.dumps({'model': 'deepseek-flash', 'sources': 12}) + '\n\n']
    frames += ['event: token\ndata: ' + json.dumps({'t': raw[i:i + 24]}) + '\n\n' for i in range(0, len(raw), 24)]
    frames.append('event: stage\ndata: {"stage": "checking"}\n\n')
    if reject:
        frames.append('event: error\ndata: ' + json.dumps({'error': 'The model returned an invalid or unsupported plan. Try again; the prior plan is unchanged.'}) + '\n\n')
    else:
        done = dict(plan, provider='deepseek', elapsed_ms=4100, usage={'prompt_tokens': 1245, 'completion_tokens': 744})
        frames.append('event: done\ndata: ' + json.dumps(done) + '\n\n')
    return ''.join(frames)


@scenario('live_ai', 'Seller watches AI draft live; checks reject the first draft and AI redrafts')
def live_ai(r: Run):
    calls = {'n': 0}
    def handle(route):
        calls['n'] += 1
        route.fulfill(status=200, content_type='text/event-stream', body=sse_body(ADVENT_PLAN, reject=calls['n'] == 1))
    r.page.route('**/api/draft', handle)
    r.page.reload(); r.page.wait_for_timeout(700)
    r.check('Live AI indicator shows when AI is connected', 'Live AI' in r.text('.ai-topbar'), r.text('.ai-topbar')[:120])
    go_focus(r); r.click('#ai-stage [data-account="advent"]', 'Open Advent')
    r.click('#ai-stage [data-build-plan]', 'Draft with AI')
    r.page.locator('#ai-run-checks:not([hidden])').wait_for(timeout=15000)
    run = r.text('#ai-stage'); r.shot('live_ai_run')
    r.check('Run view shows the five sections written live', all(x in run for x in ('one view of LP obligations', 'Compliance or legal leadership', 'Lead with the fundraise')), run[:500])
    r.check('A draft that says "investor obligations" reaches the seller as "LP obligations"', 'investor obligations' not in run and 'LP obligations' in run, run[:300])
    r.check('Rejected first draft is shown and AI redrafts once', calls['n'] == 2 and 'rejected the first draft' in run, (calls['n'], run[:300]))
    r.check('Check results are listed before review', 'claims cite this account' in run and 'left unknown, not guessed' in run)
    r.page.locator('#ai-plan-action').wait_for(state='visible', timeout=15000)
    body = r.text('#ai-stage'); r.shot('live_ai_plan')
    r.check('Plan opens with the AI run summary', 'AI draft' in body and 'run summary' in body and '1245 / 744' in body, body[:400])
    r.check('The reviewed plan uses the LP wording too', 'investor obligations' not in body and 'LP obligations' in body, body[:400])


HGGC_PLAN = {
    'account_id': 'hggc',
    'fields': [
        {'id': 'goals', 'label': 'Goals', 'basis': 'unknown', 'source_ids': [], 'value': 'Unknown: HGGC has not said what it wants from side letter obligations work.'},
        {'id': 'pain', 'label': 'Pain to confirm', 'basis': 'hypothesis', 'source_ids': ['DEMO-HOLD-001'],
         'value': 'Hypothesis: Weekly users fell from 22 to 11 while one escalation is open; confirm what is driving the drop.'},
        {'id': 'people', 'label': 'Who to talk to', 'basis': 'hypothesis', 'source_ids': ['CT-45fdef981a35-profile'],
         'value': 'Hypothesis: Cecilia Kwan, CFO, may sponsor the fix; confirm with the account owner.'},
        {'id': 'strategy', 'label': 'Angle', 'basis': 'hypothesis', 'source_ids': ['DEMO-HOLD-001'],
         'value': 'Hypothesis: Hold expansion; get the account owner and customer success on one plan to fix the issue.'},
        {'id': 'next_action', 'label': 'Next move', 'basis': 'unknown', 'source_ids': [],
         'value': 'Unknown: Whether the customer is ready to talk about more scope. Fix the open issue first.'},
    ],
    'questions': ['What does the account owner know about the escalation so far?'],
    'actions': ['Hold expansion outreach until the issue is fixed.'],
    'email': {'contact_id': 'CT-9958bb32b128-profile', 'subject': 'Fix date for the open ticket',
              'body': 'Hi Rachel, I want to acknowledge the document processing delays plainly. Could we take 20 minutes this week to agree the fix?'},
}


@scenario('trust', 'Skeptical buyer clicks off the happy path: other accounts, customers, example data')
def trust(r: Run):
    r.page.route('**/api/draft', lambda route: route.fulfill(status=200, content_type='text/event-stream', body=sse_body(HGGC_PLAN)))
    r.page.reload(); r.page.wait_for_timeout(700)
    go_focus(r); r.click('[data-open-value]', 'Time back'); tb = r.text('.ai-modal')
    r.check('Time back shows no AI run before one has happened', 'Your last AI draft' not in tb, tb[-300:])
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.click('.ai-sidebar [data-nav="accounts"]', 'Open Accounts'); r.page.wait_for_timeout(300)
    rows = r.page.evaluate("() => [...document.querySelectorAll('#ai-stage .ai-queuerow')].map(x => x.innerText)")
    fp = next((x for x in rows if 'Francisco' in x), ''); ax = next((x for x in rows if 'Audax' in x), '')
    r.check('Event labels match the event: Francisco a fund close, Audax not', 'Fund close' in fp and 'Fund close' not in ax, (fp[:140], ax[:140]))
    r.click('#ai-stage [data-account="francisco"]', 'Open Francisco'); r.page.wait_for_timeout(300)
    page = r.text('#ai-stage')
    r.check('Francisco "Why now" shows its own Jul 23 fund close, not "no trigger"', 'Fund close · Jul 23' in page and 'No dated trigger yet' not in page, page[:700])
    r.click('.ai-sidebar [data-nav="accounts"]', 'Back to Accounts'); r.page.wait_for_timeout(200)
    r.click('#ai-stage [data-account="hggc"]', 'Open HGGC'); r.page.wait_for_timeout(300)
    r.check('Made-up customer usage is labeled Simulated data where it shows', 'Simulated data' in r.text('#ai-stage'))
    r.click('#ai-stage h2 .ai-simtag', 'Open the simulated record'); ev = r.text('.ai-modal')
    r.check('The label opens the record: the usage numbers and the Simulated data label', '22 to 11' in ev and 'Simulated data' in ev and 'Made up' in ev, ev[:300])
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.click('#ai-stage [data-build-plan]', 'Prepare HGGC campaign')
    r.page.locator('#ai-plan-action').wait_for(state='visible', timeout=40000)
    body = r.text('#ai-stage'); r.shot('hggc_plan')
    msg = r.page.evaluate("() => [...document.querySelectorAll('#ai-stage textarea')].map(t => t.value).join('\\n')")
    blob = (body + '\n' + msg).lower(); words = [w for w in ('fictional', 'illustrative', 'demo hold', 'scenario') if w in blob]
    r.check('HGGC campaign has no demo wording', not words, words)
    r.check("Customer email doesn't ask the customer an internal question", 'account owner know' not in msg, msg[:400])
    r.check('Customer email is the AI draft to the named contact, signed by the seller', 'Hi Rachel,' in msg and 'acknowledge the document processing delays' in msg and msg.strip().split('\n')[0] != 'Hello,', msg[:300])
    r.check('Named contact shows on the campaign', 'Rachel Stock' in body, body[:300])
    cite = r.page.locator('#ai-stage p.ai-citerow .ai-cite.sim').first
    cite.click(); r.clicks += 1; r.page.wait_for_timeout(200); ev = r.text('.ai-modal')
    r.check('A cited usage claim opens its evidence with the simulated label', 'Simulated data' in ev and 'weekly active users 22 to 11' in ev, ev[:300])
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.check('Next action is the short playbook step', r.page.input_value('#ai-plan-action').startswith('Get the account team'), r.page.input_value('#ai-plan-action'))


@scenario('demo_path', 'Interviewer picks Advent or Francisco and asks: why this account, and what next?')
def demo_path(r: Run):
    r.page.route('**/api/draft', lambda route: route.fulfill(status=200, content_type='text/event-stream', body=sse_body(ADVENT_PLAN)))
    r.page.reload(); r.page.wait_for_timeout(700)
    go_focus(r); r.click('[data-open-value]', 'Time back'); tb = r.text('.ai-modal')
    r.check('Before any live draft, Time back shows a saved example, labeled as one', 'Saved example' in tb and 'Your last AI draft' not in tb, tb[-300:])
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    focus = r.text('#ai-stage')
    r.check('Every account shows a stage; none invents a prior touch or meeting', 'Researching · No recent touch' in focus and 'Last touch' not in focus and 'Meeting booked' not in focus, focus[:500])
    r.click('#ai-stage [data-account="advent"]', 'Open Advent'); r.page.wait_for_timeout(300)
    hot = r.text('#ai-stage .ai-whyhot'); r.shot('advent_why_hot')
    r.check('Why hot separates the public fundraise from simulated buyer activity', 'Why hot' in hot and 'Public source' in hot and 'Simulated activity' in hot and '$30 billion' in hot, hot[:500])
    r.check('The strongest buyer signal leads', hot.find('Strongest buyer signal') != -1 and hot.find('Strongest buyer signal') < hot.find('Public source'), hot[:300])
    r.check('Seller calls and emails are not counted as buyer signals', 'Call with Heather' not in hot and 'Intro email' not in hot, hot[:400])
    page = r.text('#ai-stage')
    r.check('Buyer access names the sourced people behind the points', 'Heather Zuzenak, named and sourced (1)' in page, page[:300])
    r.click('#ai-stage [data-tab="activity"]', 'Activity tab'); act = r.text('#ai-stage')
    r.check('Activity is labeled simulated and shows buyer signals only, no invented seller contact', 'Simulated activity' in act and 'Buyer activity' in act and 'Your activity' not in act and 'Coming up' not in act, act[:500])
    r.click('#ai-stage [data-build-plan]', 'Prepare campaign')
    r.page.locator('#ai-plan-action').wait_for(state='visible', timeout=20000)
    body = r.text('#ai-stage'); subject = r.page.input_value('#ai-message-subject'); msg = r.page.input_value('#ai-message')
    r.check('Email is the AI draft to the named contact: first outreach, no invented call or meeting', subject == 'Side letters across the new funds' and msg.startswith('Hi Heather,') and 'pre-read' not in msg.lower() and 'call on' not in msg and msg.strip().endswith('Claudio') and 'Alex' not in msg, (subject, msg[:300]))
    r.check('Next action is first outreach, not meeting prep', r.page.input_value('#ai-plan-action').startswith('Email Heather') and 'meeting' not in r.page.input_value('#ai-plan-action').lower(), r.page.input_value('#ai-plan-action'))
    r.fill('#ai-plan-action', EDIT, 'Edit next action'); r.click('#ai-approve-plan', 'Approve plan')
    r.page.reload(); r.page.wait_for_timeout(700); go_focus(r)
    focus = r.text('#ai-stage'); r.shot('focus_after_approval')
    r.check('After refresh, My focus shows the exact edited task, marked approved', EDIT in focus and 'Approved' in focus, focus[:500])
    r.click('#ai-stage [data-catchup]', 'Catch me up'); r.click('[data-catch-run]', 'Prepare'); r.page.locator('.ai-weekplan').wait_for(timeout=5000); cu = r.text('.ai-modal')
    first = r.page.locator('.ai-modal .ai-weekplan > li').first.inner_text()
    r.check('Catch-me-up plan carries the approved Advent task, no longer marked Suggested', EDIT in first and 'Suggested' not in first and 'build and approve the Advent' not in cu, first[:400])
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.click('[data-open-value]', 'Time back'); tb = r.text('.ai-modal')
    r.check('After a live draft, Time back shows that run', 'Your last AI draft' in tb and 'Saved example' not in tb, tb[-300:])
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.click('.ai-sidebar [data-nav="accounts"]', 'Open Accounts'); r.page.wait_for_timeout(300)
    rows = r.page.evaluate("() => [...document.querySelectorAll('#ai-stage .ai-queuerow')].map(x => x.innerText)")
    fp = next((x for x in rows if 'Francisco' in x), '')
    r.click('#ai-stage [data-account="francisco"]', 'Open Francisco'); r.page.wait_for_timeout(300)
    page = r.text('#ai-stage'); r.shot('francisco_account')
    agree = 'Jul 23' in fp and 'Fund close' in fp and 'Fund close · Jul 23' in page and 'Fund event Jul 23, 2026' in page and '$21 billion' in page and 'October fundraise' not in page
    r.check('Francisco: list row, score, Why now and What we know all use its Jul 23 fund close', agree, (fp[:120], page[:400]))
    r.check('Francisco: the cooling event shows how much credit it earns', '2.8 of 4 timing points' in page, page[:600])
    r.click('.ai-sidebar [data-nav="accounts"]', 'Back to Accounts'); r.page.wait_for_timeout(200)
    r.click('#ai-stage [data-account="gtcr"]', 'Open GTCR'); r.page.wait_for_timeout(300); page = r.text('#ai-stage')
    r.check('Role-only credit is shown where the holder is not confirmed', 'Jeff Wright, role to re-confirm (0.5)' in page, page[:400])


@scenario('weekly_plan', 'Seller plans the week: all five accounts at once, with the people and titles to work')
def weekly_plan(r: Run):
    go_focus(r); r.click('#ai-stage [data-brief-kind="weekly"]', 'Weekly brief')
    intro = r.text('.ai-modal')
    r.check('Brief dialog describes a plan for the week, not a daily rota', 'plan for the week' in intro.lower() and 'people and titles' in intro, intro[:300])
    r.click('#ai-compose-brief', 'Prepare brief'); r.page.locator('#ai-save-brief').wait_for(timeout=5000)
    brief = r.text('.ai-modal'); r.shot('weekly_plan')
    rows = r.page.locator('.ai-modal .ai-weekplan').first.locator('> li')
    names = [rows.nth(i).locator('.ai-inlineaccount').inner_text() for i in range(rows.count())]
    r.check('Five accounts in score order: Advent, Francisco, Battery Ventures, Audax, GI', names == ['1. Advent International', '2. Francisco Partners', '3. Battery Ventures', '4. Audax Private Equity', '5. GI Partners'], names)
    r.check('The plan starts with the priority accounts and leaves the choice to the seller', 'Start with these priority accounts' in brief and 'every day' not in brief, brief[:200])
    r.check('No one-account-per-day rota', not re.search(r'(?im)^\s*(mon|tue|wed|thu|fri)(day)?\b', brief) and 'first five days' not in brief.lower(), brief[:300])
    people = [rows.nth(i).locator('.ai-weekpeople li').all_inner_texts() for i in range(rows.count())]
    r.check('Every account names people with their titles', all(len(p) >= 2 and all(',' in x for x in p) for p in people), people)
    r.check('Two people per account before any meeting is booked', [len(p) for p in people] == [2, 2, 2, 2, 2], [len(p) for p in people])
    r.check('Advent lists its potential champion and budget owner (no one engaged yet)', [x.split(',')[0] for x in people[0]] == ['Heather Zuzenak', 'Susan Gentile'], people[0])
    r.check('Buying roles are labeled as possibilities, not facts', 'Potential champion' in people[1][0] and 'Potential budget owner' in people[1][1], people[1])
    r.check('Each account carries this week\'s move', r.page.locator('.ai-modal .ai-weekmove').count() == 7, r.page.locator('.ai-modal .ai-weekmove').count())
    r.check('Customers follow under Customer priorities, with their people', 'Customer priorities' in brief and 'Rachel Stock, General Counsel and Chief Compliance Officer' in brief and 'TA Associates' in brief, brief[-500:])
    before = brief
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    go_focus(r); r.click('#ai-stage [data-brief-kind="weekly"]', 'Weekly brief again'); r.click('#ai-compose-brief', 'Prepare brief'); r.page.locator('#ai-save-brief').wait_for(timeout=5000)
    r.check('Same inputs give the same plan, word for word', r.text('.ai-modal') == before)
    r.click('#ai-save-brief', 'Save brief')


@scenario('battery_and_contacts', 'Seller opens the new account and clicks on people')
def battery_and_contacts(r: Run):
    go_focus(r); r.click('#ai-stage [data-account="battery"]', 'Open Battery Ventures'); r.page.wait_for_timeout(300)
    page = r.text('#ai-stage'); r.shot('battery_account')
    r.check('Battery Ventures ranks third at 7.1, P2', '7.1' in page and 'P2' in page, page[:200])
    r.check('Its Feb 18 fund close is a cooling trigger with its timing credit shown', 'Fund close · Feb 18' in page and 'Trigger cooling (1.1 of 4 timing points)' in page and 'Fund event Feb 18, 2026' in page, page[:700])
    r.check('Its signal is a public source; nothing simulated on this account', 'Public source' in page and 'Simulated' not in page, page[:500])
    r.check('Buyer access names the sourced General Counsel and CCO', 'Lizette Perez-Deisboeck, named and sourced (1)' in page, page[:600])
    r.click('#ai-stage .ai-whyhot .ai-cite', 'Open the fund close evidence'); ev = r.text('.ai-modal')
    r.check('The fund close opens as a dated public source with a link', 'Public source' in ev and 'Feb 18, 2026' in ev and r.page.locator('.ai-modal a[href^="https://www.battery.com/"]').count() == 1, ev[:300])
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    for acct, who, title in (('battery', 'Lizette Perez-Deisboeck', 'General Counsel and Chief Compliance Officer'), ('francisco', 'Steve Eisner', 'Partner, General Counsel'), ('hggc', 'Rachel Stock', 'General Counsel and Chief Compliance Officer'), ('advent', 'Heather Zuzenak', 'Chief Compliance Officer')):
        r.click('.ai-sidebar [data-nav="accounts"]', 'Accounts'); r.click(f'#ai-stage [data-account="{acct}"]', f'Open {acct}')
        r.click('#ai-stage [data-tab="people"]', 'People tab'); r.page.wait_for_timeout(200)
        r.click('#ai-stage [data-person]', f'Open {who}'); card = r.text('.ai-modal') if r.page.locator('.ai-modal').count() else ''
        r.check(f'{acct}: clicking a person opens their profile with title, firm and source link', who in card and title in card and 'Role checked against the firm biography' in card and r.page.locator('.ai-modal a[target="_blank"]').count() == 1, card[:300])
        r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.click('#ai-stage [data-tab="people"]', 'People tab'); head = r.text('#ai-stage')
    r.check('People header carries the date the profiles were checked', 'Reviewed Nov 12, 2026' in head, head[:400])
    r.click('.ai-sidebar [data-nav="accounts"]', 'Accounts'); r.click('#ai-stage [data-account="battery"]', 'Open Battery'); r.click('#ai-stage [data-build-plan]', 'Prepare campaign')
    r.page.locator('#ai-plan-action').wait_for(state='visible', timeout=40000)
    r.click('#ai-stage [data-modal="choose-person"]', 'Change contact'); choose = r.text('.ai-modal')
    r.check('Change contact lists this account\'s own people', 'Chris Schiavo' in choose and 'Karen Bommart' in choose and 'Heather Zuzenak' not in choose, choose[:400])
    r.page.locator('.ai-modal [data-select-person]').nth(1).click(); r.clicks += 1; r.page.wait_for_timeout(300)
    r.check('Choosing a contact updates the campaign', 'Chris Schiavo' in r.text('#ai-stage .ai-entry'), r.text('#ai-stage .ai-entry'))
    r.click('.ai-sidebar [data-nav="accounts"]', 'Accounts'); rows = r.text('#ai-stage'); r.click('#ai-stage [data-account="thoma"]', 'Open Thoma Bravo'); r.page.wait_for_timeout(300); tb = r.text('#ai-stage')
    r.check('Thoma Bravo: its Jun 3, 2025 fund close reads as over a year old in the score, Why now and What we know', 'Last relevant fund event (Jun 3, 2025) is over a year old.' in tb and 'Fund close · Jun 3, 2025. Older fund event (0 of 4 timing points).' in tb and 'Announced Jun 3, 2025.' in tb and 'No dated fund event on file' not in tb and 'No dated trigger yet' not in tb, tb[:900])
    r.check('Thoma Bravo: the Accounts row says Older fund event', 'Good fit · Older fund event' in rows, rows[:600])


@scenario('tour', 'New seller takes the product tour')
def tour(r: Run):
    r.click('.ai-sidebar [data-tour-start]', 'Take the product tour')
    titles, marked = [], []
    for i in range(10):
        r.page.locator('#ai-tour h2').wait_for(timeout=5000)
        titles.append(r.page.inner_text('#ai-tour h2'))
        r.page.wait_for_timeout(250)
        marked.append(r.page.locator('#ai-stage .ai-tourtarget').count() == 1)
        if i == 4:
            r.check('Tour offers to draft live', r.page.locator('[data-tour-run]').count() == 1)
        r.click('[data-tour-next]', f'Tour step {i + 1}')
    r.check('Tour walks all ten steps in order', titles[0] == 'Your accounts, ranked' and titles[4] == 'Watch AI draft the campaign' and titles[8] == 'From reply to discovery meeting' and titles[-1] == 'Your weekly brief', titles)
    r.check('Each step highlights what it explains', all(marked), marked)
    r.check('Finish closes the tour', r.page.locator('#ai-tour').count() == 0 and r.page.locator('.ai-tourtarget').count() == 0)
    r.click('.ai-sidebar [data-modal="seller-guide"]', 'Seller Q&A')
    r.click('.ai-modal [data-tour-start]', 'Tour from Q&A')
    r.check('Tour also starts from Seller Q&A', r.page.locator('#ai-tour h2').count() == 1 and r.page.locator('.ai-modal').count() == 0)
    r.page.keyboard.press('Escape'); r.page.wait_for_timeout(200)
    r.check('Escape ends the tour', r.page.locator('#ai-tour').count() == 0)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--url', default='http://127.0.0.1:8767/'); ap.add_argument('--out', default='docs/simulations')
    a = ap.parse_args(); out = Path(a.out); shots = out / 'screens'; shots.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for key, persona, (w, h), fn in SCENARIOS:
            ctx = browser.new_context(viewport={'width': w, 'height': h}, reduced_motion='reduce' if key == 'stress' else 'no-preference')
            if key == 'no_storage':
                ctx.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})")
            if key == 'ai_failure':
                ctx.route('**/api/status', lambda route: route.fulfill(status=200, content_type='application/json', body='{"configured":true,"provider":"deepseek","model":"deepseek-flash"}'))
                ctx.route('**/api/plan', lambda route: route.fulfill(status=502, content_type='application/json', body='{"error":"Simulated provider outage"}'))
                ctx.route('**/api/draft', lambda route: route.fulfill(status=502, content_type='application/json', body='{"error":"Simulated provider outage"}'))
            elif key in ('live_ai', 'trust', 'demo_path'):
                ctx.route('**/api/status', lambda route: route.fulfill(status=200, content_type='application/json', body='{"configured":true,"provider":"deepseek","model":"deepseek-flash"}'))
            else:
                ctx.route('**/api/status', lambda route: route.fulfill(status=404, body='not found'))
                ctx.route('**/api/plan', lambda route: route.fulfill(status=404, body='not found'))
                ctx.route('**/api/draft', lambda route: route.fulfill(status=404, body='not found'))
            page = ctx.new_page(); r = Run(page, shots, key)
            page.goto(a.url); page.wait_for_timeout(500)
            try:
                page.evaluate('localStorage.clear()')
            except Exception:
                pass
            page.reload(); page.wait_for_timeout(700)
            status = 'ok'
            try:
                fn(r)
            except Exception as e:  # a crash is a failed check, not a crashed suite
                status = 'error'; r.check('Scenario completed without crashing', False, repr(e)[:300])
                try: r.shot('error')
                except Exception: pass
            r.check('No script errors', not r.errors, r.errors[:3])
            results.append({'scenario': key, 'persona': persona, 'viewport': f'{w}x{h}', 'status': status, 'clicks': r.clicks,
                            'elapsed_ms': round((time.perf_counter() - r.t0) * 1000), 'milestones': r.marks, 'steps': r.steps, 'checks': r.checks})
            ctx.close()
        browser.close()
    total = sum(len(x['checks']) for x in results); passed = sum(c['pass'] for x in results for c in x['checks'])
    report = {'run_at': datetime.now().isoformat(timespec='seconds'), 'url': a.url, 'model_calls': 0, 'checks_passed': passed, 'checks_total': total, 'scenarios': results}
    (out / 'simulation_results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = [f"# Seller simulations — {report['run_at']}", '', f"{passed}/{total} checks passed · {len(results)} scenarios · 0 model calls (recorded run and forced failure only)", '']
    for x in results:
        ok = sum(c['pass'] for c in x['checks'])
        lines += [f"## {x['scenario']} — {x['persona']}", f"Viewport {x['viewport']} · {x['clicks']} clicks · {ok}/{len(x['checks'])} checks"]
        for m, v in x['milestones'].items(): lines.append(f"- Milestone **{m.replace('_', ' ')}**: {v['clicks']} clicks, {v['ms']/1000:.1f} s automated")
        for c in x['checks']: lines.append(f"- {'PASS' if c['pass'] else 'FAIL'} · {c['check']}" + ('' if c['pass'] else f" — {c['detail']}"))
        lines.append('')
    (out / 'SIMULATION_REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'passed': passed, 'total': total, 'report': str(out / 'SIMULATION_REPORT.md')}))
    for x in results:
        for c in x['checks']:
            if not c['pass']: print('FAIL', x['scenario'], c['check'], c['detail'])


if __name__ == '__main__':
    main()
