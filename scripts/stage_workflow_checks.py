"""Two-stage sales workflow: initial outreach (no invented contact) -> recorded reply -> confirmed meeting -> internal pre-call plan
-> seller notes -> tasks, daily brief, calendar drafts and PDF agree. No model call (/api/status forced off; the saved Advent run replays).
Usage: python scripts/stage_workflow_checks.py [url] [out_dir]"""
import json, sys, re, pathlib
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8767/'
out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else 'docs/stage_workflow'); out.mkdir(parents=True, exist_ok=True)
EDIT = 'Email Heather today: ask how side letter obligations from GPE XI are tracked, and who owns them.'
NOTE_SAID = 'Obligations live in a spreadsheet per fund; Legal and Compliance keep separate copies.'
AGREED = 'Send Heather and Brian a two-page summary and hold 30 minutes with Legal next week.'
BLOCK = 'Brian must confirm Legal can join before we schedule.'
checks = []
def check(label, ok, detail=''):
    checks.append({'label': label, 'ok': bool(ok), 'detail': '' if ok else str(detail)[:400]})
    print(('PASS ' if ok else 'FAIL ') + label + ('' if ok else '  ::  ' + str(detail)[:300]))
def store(p): return p.evaluate("() => JSON.parse(localStorage.getItem('account-intelligence-seller-workflow-v1') || '{}')")
def open_advent(p, tab=None):
    p.click('.ai-sidebar [data-nav="accounts"]'); p.wait_for_timeout(300)
    p.click('#ai-stage [data-account="advent"]'); p.wait_for_timeout(400)
    if tab: p.click(f'#ai-stage [data-tab="{tab}"]'); p.wait_for_timeout(400)

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 1440, 'height': 900})
    ctx.add_init_script("window.__printed=0; window.print=()=>{window.__printed++;};")
    p = ctx.new_page(); errs = []
    p.on('pageerror', lambda e: errs.append(str(e)))
    p.route('**/api/status', lambda r: r.fulfill(status=404, body='off'))
    p.goto(url); p.wait_for_selector('#ai-stage'); p.wait_for_timeout(800)

    # ---------- A. initial outreach: nothing invented ----------
    focus = p.inner_text('#ai-stage')
    adv_row = focus.split('Advent International')[1][:260]
    check('My focus: Advent is Researching with no recent touch', 'Researching · No recent touch' in adv_row, adv_row)
    check('My focus: no booked meeting or prior email anywhere', 'Meeting booked' not in focus and 'Outreach started' not in focus and 'Last touch' not in focus, re.findall(r'Meeting booked|Outreach started|Last touch[^\n]*', focus))
    check('Wording: Your priority accounts and Customer priorities on My focus', 'Your priority accounts' in focus and 'Customer priorities' in focus and 'Defend the house' not in focus and 'Top five' not in focus)
    open_advent(p)
    ov = p.inner_text('#ai-stage')
    check('Account overview tab, People to contact, Why prioritize this account', 'Account overview' in ov and 'People to contact' in ov and 'Why prioritize this account' in ov, '')
    check('Advent overview: stage Researching, no prior call or known pain', 'Stage\nResearching' in ov and not re.search(r'Nov 11|opened your|Intro email|call with', ov, re.I), re.findall(r'Stage\n\w+', ov))
    check('Advent next action is first outreach, not meeting prep', 'Email Heather Zuzenak: ask how side letter obligations from the new funds are tracked' in ov and 'meeting' not in ov.split('Recommended next action')[1][:200].lower(), ov.split('Recommended next action')[1][:200] if 'Recommended next action' in ov else '')
    p.click('#ai-stage [data-tab="activity"]'); p.wait_for_timeout(300)
    act = p.inner_text('#ai-stage')
    check('Activity: buyer signals only, labelled simulated, no seller contact', 'Simulated activity' in act and 'Your activity' not in act and 'Coming up' not in act, act[:400])
    p.click('#ai-stage [data-tab="meeting"]'); p.wait_for_timeout(300)
    mt = p.inner_text('#ai-stage')
    check('Discovery meeting tab: no reply recorded, initial outreach, simulated label', 'No reply recorded' in mt and 'initial outreach' in mt and 'Simulated' in mt, mt[:300])
    qual0 = p.evaluate("() => document.querySelector('#ai-stage') && 1")

    # campaign (saved live run replays), plan preview, approve
    p.click('#ai-stage [data-build-plan]'); p.locator('#ai-plan-action').wait_for(state='visible', timeout=40000); p.wait_for_timeout(300)
    plan = p.inner_text('#ai-stage')
    check('Plan preview has no hardcoded Nov 16/17 dates', 'Due Nov 16' not in plan and 'Due Nov 17' not in plan and 'Not scheduled' in plan, re.findall(r'Due Nov \d+', plan))
    msg = p.input_value('#ai-message')
    check('Outreach email: no prior call, meeting or tracking mentioned', msg.startswith('Hi Heather') and not re.search(r'thanks for the call|our call|Nov 11|pre-read|walkthrough|viewed|visited|looked at|opened', msg, re.I), msg[:300])
    p.fill('#ai-plan-action', EDIT); p.click('#ai-approve-plan'); p.wait_for_timeout(600)
    toast = p.inner_text('#ai-toast')
    check('Approve: qualification unchanged message', 'qualification unchanged' in toast, toast)
    open_advent(p, 'meeting')
    check('Approval alone does not advance the buyer: still Researching, no reply', 'Stage: Researching' in p.inner_text('#ai-stage') and 'No reply recorded' in p.inner_text('#ai-stage'))
    p.click('.ai-sidebar [data-nav="tasks"]'); p.wait_for_timeout(400)
    tk = p.inner_text('#ai-stage')
    check('My tasks: exact reviewed action under Not scheduled with Set date', 'NOT SCHEDULED' in tk.upper() and EDIT in tk and p.locator('#ai-stage [data-task-due]').count() == 2 and 'Set date' in tk, tk[:500])
    check('No calendar button before a date is set', p.locator('#ai-stage [data-cal-open]').count() == 0)
    p.fill('[data-task-due="advent-0"]', '2026-11-17'); p.dispatch_event('[data-task-due="advent-0"]', 'change'); p.wait_for_timeout(400)
    tk = p.inner_text('#ai-stage')
    check('Dated task moves under Scheduled with Due Nov 17 and a calendar draft', 'SCHEDULED' in tk.upper() and 'Due Nov 17' in tk and p.locator('#ai-stage [data-cal-open="advent-0"]').count() == 1, tk[:300])
    q = parse_qs(urlparse(p.get_attribute('[data-cal-open="advent-0"]', 'href')).query)
    check('Outreach calendar draft: exact action, Nov 17, LA time, no guests', q.get('text') == ['Advent International: ' + EDIT] and q.get('dates') == ['20261117/20261118'] and q.get('ctz') == ['America/Los_Angeles'] and 'add' not in q, q)

    # weekly brief save must not approve or create tasks
    before = store(p); n_tasks = len(before.get('tasks', [])); approved = sorted(k for k, v in before.get('plans', {}).items() if v.get('approved'))
    p.click('.ai-sidebar [data-nav="focus"]'); p.wait_for_timeout(300)
    p.click('#ai-stage [data-brief-kind="weekly"]'); p.wait_for_timeout(300); p.click('#ai-compose-brief'); p.locator('#ai-save-brief').wait_for(timeout=5000)
    wk = p.inner_text('.ai-modal')
    check('Weekly brief: Customer priorities, edited action, others Suggested', 'Customer priorities' in wk and EDIT in wk and wk.count('Suggested') >= 4, '')
    p.click('#ai-save-brief'); p.wait_for_timeout(400)
    after = store(p)
    check('Saving the weekly brief creates no tasks and approves nothing', len(after.get('tasks', [])) == n_tasks and sorted(k for k, v in after.get('plans', {}).items() if v.get('approved')) == approved, (n_tasks, len(after.get('tasks', []))))

    # ---------- B. recorded reply -> confirmed meeting -> pre-call plan ----------
    open_advent(p, 'meeting')
    p.click('#ai-rr-save'); p.wait_for_timeout(300)
    check('A reply cannot be recorded without what the buyer said', 'No reply recorded' in p.inner_text('#ai-stage'))
    p.click('#ai-rr-sim'); p.click('#ai-rr-save'); p.wait_for_timeout(500)
    mt = p.inner_text('#ai-stage')
    check('Reply recorded: labelled simulated, stage Positive reply, not booked', 'Recorded by you · simulated' in mt and 'Stage: Positive reply' in mt and 'Meeting booked' not in mt, mt[:400])
    check('Next step suggested: book a discovery call (reviewed-action flow)', 'Book a 30-minute discovery call with Heather.' in p.input_value('#ai-mt-action'))
    p.click('#ai-mt-approve'); p.wait_for_timeout(400)
    st = store(p)
    check('Approving the next step adds that exact task, undated', any(t['id'] == 'advent-m' and t['text'] == 'Book a 30-minute discovery call with Heather.' and not t.get('due') for t in st['tasks']))
    p.fill('#ai-mt-date', '2026-11-19'); p.fill('#ai-mt-time', '10:00')
    brian = p.locator('#ai-stage [data-att]').filter(has=p.locator('xpath=.')).all()
    p.evaluate("""() => { const row = [...document.querySelectorAll('#ai-stage .ai-attrow')].find(r => /Brian Busch/.test(r.innerText)); row.querySelector('[data-att]').checked = true; }""")
    p.click('#ai-mt-save'); p.wait_for_timeout(400)
    mt = p.inner_text('#ai-stage')
    check('Saved meeting details are not a booked meeting', 'Stage: Positive reply' in mt and p.locator('#ai-mt-confirm').count() == 1, mt[:200])
    href = p.get_attribute('#ai-stage [data-meet-cal]', 'href'); mq = parse_qs(urlparse(href).query)
    check('Meeting calendar draft: Nov 19 10:00–10:30 PT, agenda only, no guests', mq.get('dates') == ['20261119T100000/20261119T103000'] and mq.get('ctz') == ['America/Los_Angeles'] and 'add' not in mq and 'Proposed agenda' in mq.get('details', [''])[0] and 'Hypothesis' not in mq.get('details', [''])[0], mq)
    with ctx.expect_page(timeout=10000) as pop:
        p.click('#ai-stage [data-meet-cal]')
    pop.value.close()
    check('Opening the meeting draft says it does not book the meeting', 'does not book the meeting' in p.inner_text('#ai-toast') and 'Stage: Positive reply' in p.inner_text('#ai-stage'))
    p.click('#ai-mt-confirm'); p.wait_for_timeout(600)
    pc = p.inner_text('#ai-stage')
    (out / 'precall_plan.txt').write_text(pc, encoding='utf-8')
    check('Confirmed by the seller: stage Meeting booked', 'Stage: Meeting booked' in pc, pc[:200])
    for label, needle in [('objective', 'Understand how Advent International tracks LP obligations today'), ('status', 'Confirmed by you'), ('date and time', 'Thu, Nov 19, 10:00 a.m. PT · 30 min'),
                          ('meeting owner shown separately', 'Claudio Aversa (you, seller)'), ('primary prospect', 'Heather Zuzenak'), ('attendee unconfirmed', 'Brian Busch'),
                          ('why now with public source', 'Public source'), ('shareable agenda', 'Can be shared with the buyer'), ('internal discovery prep', 'Discovery preparation'),
                          ('unknowns', 'Unknown until the buyer says'), ('preparation tasks', 'Confirm whether Brian Busch is joining'), ('notes area', 'Discovery notes')]:
        check(f'Pre-call plan has {label}', needle.lower() in pc.lower(), needle)
    check('Attendance shown as Unconfirmed for Brian', re.search(r'Brian Busch.*Unconfirmed', pc.replace('\n', ' ')) is not None)
    check('Pre-call plan: Firm profile link for the primary prospect', p.locator('#ai-stage .ai-precall a.ai-proflink[href*="heather-zuzenak"]').count() >= 1)
    agenda = p.inner_text('#ai-stage .ai-pcshare'); internal = p.inner_text('#ai-stage .ai-pcinternal')
    check('Agenda (shareable) carries no internal hypothesis', 'ypothes' not in agenda and 'spreadsheet' not in agenda.lower() and agenda.count('\n') <= 5, agenda)
    check('Hypothesis labelled as an AI suggestion, kept in the internal section', 'ai suggestion, reviewed by you' in internal.lower() and 'questions to ask' in internal.lower(), internal[:300])
    check('Before the call, buyer findings and agreed step are blank', all(p.input_value(s) == '' for s in ('#ai-pc-said', '#ai-pc-confirmed', '#ai-pc-unknown', '#ai-pc-action', '#ai-pc-date')))
    p.locator('#ai-stage .ai-precall').screenshot(path=str(out / 'precall_plan_desktop.png'))

    # notes after the call
    p.fill('#ai-pc-said', NOTE_SAID); p.fill('#ai-pc-confirmed', 'Compliance owns tracking; Legal drafts side letters.'); p.fill('#ai-pc-unknown', 'Budget and timing.')
    p.fill('#ai-pc-action', AGREED); p.fill('#ai-pc-owner', 'Claudio Aversa'); p.fill('#ai-pc-date', '2026-11-20')
    check('Pre-call plan has a dependencies or blockers field', p.locator('#ai-pc-blockers').count() == 1)
    if p.locator('#ai-pc-blockers').count(): p.fill('#ai-pc-blockers', BLOCK)
    p.click('#ai-pc-save'); p.wait_for_timeout(300); p.click('#ai-pc-task'); p.wait_for_timeout(400)
    p.reload(); p.wait_for_selector('#ai-stage'); p.wait_for_timeout(700)
    open_advent(p, 'meeting')
    check('Seller notes, agreed step and blockers persist after reload', p.input_value('#ai-pc-said') == NOTE_SAID and p.input_value('#ai-pc-action') == AGREED and p.input_value('#ai-pc-date') == '2026-11-20' and p.locator('#ai-pc-blockers').count() == 1 and p.input_value('#ai-pc-blockers') == BLOCK)
    check('Notes are not marked as AI suggestions', 'Entered by you after the call' in p.inner_text('#ai-stage .ai-pcnotes'))
    p.click('#ai-stage [data-tab="qualification"]'); p.wait_for_timeout(300)
    qv = p.inner_text('#ai-stage')
    check('Qualification is not set automatically by a reply, meeting or notes', 'Qualified for next step' not in qv, qv[:300])
    p.click('.ai-sidebar [data-nav="tasks"]'); p.wait_for_timeout(400); tk = p.inner_text('#ai-stage')
    check('Agreed step is a task due Nov 20; outreach still Due Nov 17; no duplicates', AGREED in tk and 'Due Nov 20' in tk and 'Due Nov 17' in tk and len(store(p)['tasks']) == len({t['id'] for t in store(p)['tasks']}), tk[:600])

    # daily brief for Nov 20, then change a task -> flagged
    p.click('#ai-stage [data-brief-kind="daily"]'); p.wait_for_timeout(300)
    p.fill('#ai-brief-date', '2026-11-20'); p.dispatch_event('#ai-brief-date', 'change')
    p.click('#ai-compose-brief'); p.locator('#ai-save-brief').wait_for(timeout=5000)
    db = p.inner_text('.ai-modal')
    check('Daily brief for Nov 20: agreed step Due Nov 20, outreach Overdue Nov 17', 'Due Nov 20' in db and AGREED in db and 'Overdue Nov 17' in db, db[:500])
    check('Daily brief: undated approved tasks counted as not scheduled', re.search(r'\d+ approved tasks? (?:is|are) not scheduled', db) is not None, db[-300:])
    p.click('#ai-save-brief'); p.wait_for_timeout(400)
    p.click('.ai-sidebar [data-nav="briefs"]'); p.wait_for_timeout(300)
    daily_row = lambda: p.locator('#ai-stage .ai-briefrow').first.inner_text()
    check('Saved daily brief is current right after saving', 'Daily action brief' in daily_row() and 'Plan updated' not in daily_row(), daily_row())
    p.click('.ai-sidebar [data-nav="tasks"]'); p.wait_for_timeout(300)
    p.locator('#ai-stage [data-task="advent-agreed"]').check(); p.wait_for_timeout(300)
    p.click('.ai-sidebar [data-nav="briefs"]'); p.wait_for_timeout(300)
    check('Completing a task flags the saved daily brief', 'Plan updated' in daily_row(), daily_row())
    # a new daily brief, then a meeting change (defect: reply and meeting changes were not noticed)
    p.click('.ai-sidebar [data-nav="tasks"]'); p.wait_for_timeout(300)
    p.click('#ai-stage [data-brief-kind="daily"]'); p.wait_for_timeout(300); p.fill('#ai-brief-date', '2026-11-20'); p.dispatch_event('#ai-brief-date', 'change')
    p.click('#ai-compose-brief'); p.locator('#ai-save-brief').wait_for(timeout=5000); p.click('#ai-save-brief'); p.wait_for_timeout(400)
    p.click('.ai-sidebar [data-nav="briefs"]'); p.wait_for_timeout(300)
    check('A fresh daily brief is current', 'Plan updated' not in daily_row(), daily_row())
    open_advent(p, 'meeting'); p.click('#ai-mt-edit'); p.wait_for_timeout(300); p.fill('#ai-mt-time', '10:30'); p.click('#ai-mt-confirm'); p.wait_for_timeout(400)
    p.click('.ai-sidebar [data-nav="briefs"]'); p.wait_for_timeout(300)
    check('Changing the meeting time flags the saved daily brief', 'Plan updated' in daily_row(), daily_row())

    # PDFs
    p.click('.ai-sidebar [data-nav="focus"]'); p.wait_for_timeout(300)
    p.click('#ai-stage [data-catchup]'); p.wait_for_timeout(300); p.click('[data-catch-run]'); p.wait_for_timeout(1000)
    p.click('.ai-modal [data-print-report]'); p.wait_for_timeout(400)
    rep = p.evaluate("() => document.getElementById('ai-print').innerText")
    check('Weekly PDF: reply and confirmed meeting with matching date and time', 'recorded by you, simulated' in rep and 'Meeting: Thu, Nov 19, 10:30 a.m. PT, confirmed by you' in rep, rep[:400])
    check('Weekly PDF: agreed step with owner, date and blockers', AGREED + ' · Claudio Aversa · Nov 20' in rep and BLOCK in rep, '')
    check('Weekly PDF: edited action and dated tasks match My tasks', EDIT in rep and 'Due Nov 17' in rep and 'Book a 30-minute discovery call with Heather.' in rep, '')
    check('Weekly PDF: new section names', 'Your priority accounts' in rep and 'Customer priorities' in rep and 'People to contact' in rep, '')
    p.emulate_media(media='print'); p.pdf(path=str(out / 'Account_Intel_weekly_plan.pdf'), format='Letter', print_background=True); p.emulate_media(media='screen')
    p.keyboard.press('Escape'); p.wait_for_timeout(300)
    open_advent(p, 'meeting')
    p.click('#ai-stage [data-print-precall]'); p.wait_for_timeout(400)
    pcp = p.evaluate("() => document.getElementById('ai-print').innerText")
    check('Pre-call PDF: internal label, agenda, hypothesis and the seller notes', 'internal pre-call plan' in pcp.lower() and 'proposed agenda' in pcp.lower() and NOTE_SAID in pcp, pcp[:300])
    check('Pre-call PDF keeps the agreed step, owner, date and blockers (defect: inputs were dropped)', AGREED in pcp and 'Claudio Aversa' in pcp.split('Agreed next step')[-1] and 'Nov 20, 2026' in pcp and BLOCK in pcp, pcp[-600:])
    p.emulate_media(media='print'); p.pdf(path=str(out / 'Advent_precall_plan.pdf'), format='Letter', print_background=True); p.emulate_media(media='screen')
    # reviewed-by-you only while the plan is approved and current (defect: label shown regardless)
    open_advent(p); p.click('#ai-stage [data-modal="research"]'); p.wait_for_timeout(300)
    p.locator('#ai-event-toggle').uncheck(force=True); p.wait_for_timeout(400); p.keyboard.press('Escape'); p.wait_for_timeout(300)
    open_advent(p, 'meeting'); tag = p.inner_text('#ai-stage .ai-pcinternal').lower()
    check('After the evidence changes, the hypothesis is no longer "reviewed by you"', 'reviewed by you' not in tag and 'not yet approved' in tag, tag[:200])
    open_advent(p); p.click('#ai-stage [data-modal="research"]'); p.wait_for_timeout(300)
    p.locator('#ai-event-toggle').check(force=True); p.wait_for_timeout(400); p.keyboard.press('Escape'); p.wait_for_timeout(300)
    # removing the reply removes the tasks that depended on it (defect: the agreed step was left behind)
    open_advent(p, 'meeting'); p.click('#ai-rr-clear'); p.wait_for_timeout(400)
    ids = [x['id'] for x in store(p).get('tasks', [])]
    check('Removing the reply removes the booking task and the agreed step', 'advent-m' not in ids and 'advent-agreed' not in ids and 'removed from My tasks' in p.inner_text('#ai-toast'), (ids, p.inner_text('#ai-toast')))
    check('After removing the reply the account is back in initial outreach', 'Stage: Researching' in p.inner_text('#ai-stage') and 'No reply recorded' in p.inner_text('#ai-stage'))
    # wording
    open_advent(p); tabs = ' | '.join(p.locator('#ai-stage .ai-tabs button').all_inner_texts())
    check('Tab reads People to contact', 'People to contact' in tabs, tabs)
    p.click('.ai-sidebar [data-nav="focus"]'); p.wait_for_timeout(300); p.click('#ai-stage [data-catchup]'); p.wait_for_timeout(300); p.click('[data-catch-run]'); p.wait_for_timeout(900)
    gaps = p.inner_text('.ai-modal .ai-cs-gaps')
    check('Gaps to close no longer calls a public title a confirmed contact', 'confirmed entry contact' not in gaps and 'confirm roles' in gaps, gaps)
    p.keyboard.press('Escape')
    check('No page errors (desktop)', not errs, errs)
    ctx.close()

    # ---------- phone + tour ----------
    ctx = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    p = ctx.new_page(); errs = []
    p.on('pageerror', lambda e: errs.append(str(e)))
    p.route('**/api/status', lambda r: r.fulfill(status=404, body='off'))
    p.goto(url); p.wait_for_selector('#ai-stage'); p.wait_for_timeout(600)
    p.click('#ai-stage [data-account="advent"]'); p.wait_for_timeout(400); p.click('#ai-stage [data-tab="meeting"]'); p.wait_for_timeout(300)
    p.click('#ai-rr-sim'); p.click('#ai-rr-save'); p.wait_for_timeout(400)
    p.fill('#ai-mt-date', '2026-11-19'); p.fill('#ai-mt-time', '10:00'); p.click('#ai-mt-save'); p.wait_for_timeout(300); p.click('#ai-mt-confirm'); p.wait_for_timeout(500)
    m = p.evaluate("() => ({w: document.documentElement.scrollWidth, vw: innerWidth})")
    check('390px: pre-call plan fits the screen', m['w'] <= m['vw'], m)
    p.screenshot(path=str(out / 'precall_plan_phone390.png'), full_page=True)
    check('No page errors (phone)', not errs, errs)
    ctx.close()

    ctx = b.new_context(viewport={'width': 1440, 'height': 900}); p = ctx.new_page(); errs = []
    p.on('pageerror', lambda e: errs.append(str(e)))
    p.route('**/api/status', lambda r: r.fulfill(status=404, body='off'))
    p.goto(url); p.wait_for_selector('#ai-stage'); p.wait_for_timeout(600)
    p.click('.ai-sidebar [data-tour-start]'); titles = []; marked = []
    for i in range(10):
        p.locator('#ai-tour h2').wait_for(timeout=5000); titles.append(p.inner_text('#ai-tour h2')); p.wait_for_timeout(250)
        marked.append(p.locator('#ai-stage .ai-tourtarget').count() == 1)
        p.click('[data-tour-next]')
    check('Tour: ten steps, includes the discovery meeting and Customer priorities', 'From reply to discovery meeting' in titles and 'Customer priorities' in titles and titles[-1] == 'Your weekly brief', titles)
    check('Tour: every step highlights its target', all(marked), list(zip(titles, marked)))
    check('No page errors (tour)', not errs, errs)
    b.close()

res = {'url': url, 'passed': sum(c['ok'] for c in checks), 'total': len(checks), 'checks': checks}
(out / 'stage_workflow_checks.json').write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding='utf-8')
print(json.dumps({k: res[k] for k in ('url', 'passed', 'total')}))
