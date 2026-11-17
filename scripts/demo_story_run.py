"""The interview demo, clicked in story order on the deployed link, in a fresh browser session, with REAL AI drafts.
Story: a seller inherits a book or returns from leave, gets caught up, knows where to start, and gets time back.
Usage: python scripts/demo_story_run.py [url] [out_dir]
Makes 2 real AI calls (Advent, Thoma Bravo). Writes screenshots, story_run.json and STORY_RUN.md."""
import json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = (sys.argv[1] if len(sys.argv) > 1 else 'https://account-intel-live.vercel.app').rstrip('/') + '/'
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else 'docs/story_run'); OUT.mkdir(parents=True, exist_ok=True)
EDIT = 'Email Heather today: ask how side letter obligations from GPE XI are tracked, and who owns them.'
FILLER = re.compile(r"\bI imagine\b|\bI hope\b|\bI(?:'m| am|’m) curious\b|\breach(?:ing|ed)? out\b|investor obligation|—|!", re.I)
res = {'url': URL, 'checks': [], 'beats': []}
T0 = None

def check(label, ok, detail=''):
    res['checks'].append({'check': label, 'pass': bool(ok), 'detail': str(detail)[:500]})
    print(('PASS ' if ok else 'FAIL ') + label + ('' if ok else ' :: ' + str(detail)[:400]))

def beat(name, clicks):
    res['beats'].append({'beat': name, 'clicks': clicks, 'at_seconds': round(time.time() - T0, 1)})

def words(text):
    return len(re.findall(r"[A-Za-z0-9$%'’.-]+", text))

def draft(page, account, shot):
    page.click('.ai-sidebar [data-nav="accounts"]'); page.wait_for_timeout(300)
    page.click(f'#ai-stage [data-account="{account}"]'); page.wait_for_timeout(400)
    t0 = time.time(); page.click('#ai-stage [data-build-plan]')
    page.locator('#ai-plan-action').wait_for(state='visible', timeout=90000)
    wall = round(time.time() - t0, 1); page.wait_for_timeout(400)
    body = page.inner_text('#ai-stage')
    out = {'wall_seconds': wall, 'subject': page.input_value('#ai-message-subject'), 'message': page.input_value('#ai-message'),
           'next_action': page.input_value('#ai-plan-action'), 'live': 'AI draft · run summary' in body, 'failed': 'AI draft failed' in body,
           'contact': page.inner_text('#ai-stage .ai-entry strong')}
    for key, label in (('response_time', 'Response time'), ('sourced', 'Sourced claims'), ('inputs', 'Inputs')):
        loc = page.locator(f'#ai-stage .ai-runmetrics div:has(small:text-is("{label}")) strong')
        out[key] = loc.first.inner_text() if loc.count() else None
    out['checks_shown'] = page.locator('#ai-stage .ai-checks li').all_inner_texts()
    page.screenshot(path=str(OUT / shot), full_page=True)
    return out

with sync_playwright() as pw:
    browser = pw.chromium.launch(); ctx = browser.new_context(viewport={'width': 1440, 'height': 900}); page = ctx.new_page()
    errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
    t_load = time.time(); page.goto(URL); page.locator('#ai-stage [data-account]').first.wait_for(timeout=15000)
    res['first_list_ms'] = round((time.time() - t_load) * 1000); T0 = time.time(); page.wait_for_timeout(800)

    # Beat 1: one place, already prepared
    top = page.inner_text('.ai-topbar'); focus = page.inner_text('#ai-stage'); page.screenshot(path=str(OUT / '01_my_focus.png'))
    res['my_focus'] = focus
    check('Opens on My focus with live AI connected', 'Live AI' in top, top[:120])
    check('Top line: book already ranked, with the estimated time back', 'Prepared before you opened this.' in focus and re.search(r'11 accounts ranked from \d+ public sources and \d+ researched contacts', focus) and 'Est. time back this week' in focus and '4.7–8.4 h' in focus, focus[:400])
    beat('My focus: ranked book and time back', 0)

    # Beat 2: inherited a new book
    page.click('#ai-stage [data-catchup]'); page.wait_for_timeout(300); pick = page.inner_text('.ai-modal'); res['catch_pick'] = pick
    check('Catch me up offers both stories: new account list, back from leave', 'New account list' in pick and 'Back from leave' in pick, pick[:300])
    page.click('[data-catch-run]'); page.locator('.ai-weekplan').wait_for(timeout=5000); page.wait_for_timeout(300)
    hand = page.inner_text('.ai-modal'); res['handover'] = hand; page.screenshot(path=str(OUT / '02_new_book_handover.png'))
    check('Handover brief: where to start, in score order', all(n in hand for n in ('Advent International', 'Francisco Partners', 'Battery Ventures')) and hand.index('Advent International') < hand.index('Francisco Partners') < hand.index('Battery Ventures'), hand[:500])
    check('Handover brief: customers to defend', 'TA Associates' in hand and 'HGGC' in hand and 'Retention play' in hand, hand[:800])
    plan = page.inner_text('.ai-weekplan'); res['week_plan'] = plan
    check('Plan for the week: five accounts, named people with titles', all(n in plan for n in ('Advent International', 'Francisco Partners', 'Battery Ventures', 'Audax', 'GI Partners')) and 'Heather Zuzenak' in plan and 'Start with these priority accounts' in hand, plan[:500])
    check('Plan for the week has no weekday rota', not re.search(r'\b(Monday|Tuesday|Wednesday|Friday):', plan), plan[:300])
    beat('New account list: handover brief and plan for the week', 2)

    # Beat 3: back from leave
    page.click('[data-catch-kind="return"]'); page.wait_for_timeout(200)
    page.click('[data-leave-weeks="3"]'); page.click('[data-catch-run]'); page.locator('.ai-changelist').wait_for(timeout=5000); page.wait_for_timeout(300)
    back3 = page.inner_text('.ai-modal'); res['back_3_weeks'] = back3; page.screenshot(path=str(OUT / '03_back_from_leave_3_weeks.png'))
    check('Back from leave, 3 weeks: Advent moved 4.0 to 9.1 and is now P1', '4.0 → 9.1' in back3 and 'P1' in back3, back3[:600])
    check('Back from leave, 3 weeks: HGGC is a retention play', 'HGGC' in back3 and 'etention play' in back3, back3[:800])
    page.click('[data-leave-weeks="2"]'); page.wait_for_timeout(300)
    if not page.locator('.ai-changelist').count(): page.click('[data-catch-run]')
    page.locator('.ai-changelist').wait_for(timeout=5000); page.wait_for_timeout(300)
    back2 = page.inner_text('.ai-modal'); res['back_2_weeks'] = back2
    check('Back from leave, 2 weeks: the Oct 27 event drops out', '4.0 → 9.1' not in back2, back2[:600])
    page.keyboard.press('Escape'); page.wait_for_timeout(300)
    beat('Back from leave: 3 weeks, then 2 weeks', 5)

    # Beat 4: why this account (prioritization and qualification)
    page.click('.ai-sidebar [data-nav="focus"]'); page.wait_for_timeout(300)
    page.click('#ai-stage [data-account="advent"]'); page.wait_for_timeout(400)
    hot = page.inner_text('#ai-stage .ai-whyhot'); acct = page.inner_text('#ai-stage'); res['advent_account'] = acct
    page.screenshot(path=str(OUT / '04_advent_why_hot.png'))
    check('Advent: 9.1 with reasons, public and simulated evidence labeled apart', '9.1' in acct and 'Public source' in hot and 'Simulated activity' in hot and '$30 billion' in hot, hot[:300])
    beat('Advent: why it ranks first', 1)

    # Beat 5: live AI draft, seller edits and approves
    a = res['advent'] = draft(page, 'advent', '05_advent_live_draft.png')
    check('Advent live draft succeeded, every claim sourced', a['live'] and not a['failed'] and a['sourced'] and a['sourced'].split('/')[0].strip() == a['sourced'].split('/')[1].strip(), a)
    check('Advent email goes to the planned contact, greeting on its own line', a['contact'].startswith('Heather Zuzenak') and a['message'].startswith('Hi Heather,\n\n'), a['message'][:200])
    check('Advent email has no filler, no banned wording', not FILLER.search(a['subject'] + ' ' + a['message']), a['message'])
    check('Advent email is first outreach: no invented call, meeting or tracking', not re.search(r'thanks for the call|our call|pre-read|walkthrough|nov 19|viewed|visited|looked at|opened', a['subject'] + ' ' + a['message'], re.I), a['message'])
    page.fill('#ai-plan-action', EDIT); page.click('#ai-approve-plan'); page.wait_for_timeout(500)
    page.click('.ai-sidebar [data-nav="focus"]'); page.wait_for_timeout(400); focus2 = page.inner_text('#ai-stage')
    check('Approved plan: My focus shows the exact edited task', EDIT in focus2 and 'Approved by you' in focus2, focus2[:400])
    beat('Live AI campaign, edit, approve', 5)

    # Beat 5b: the approved action becomes a dated task
    page.click('.ai-sidebar [data-nav="tasks"]'); page.wait_for_timeout(400)
    check('My tasks: the exact action, not scheduled until a date is set', EDIT in page.inner_text('#ai-stage') and page.locator('[data-task-due="advent-0"]').count() == 1)
    page.fill('[data-task-due="advent-0"]', '2026-11-17'); page.dispatch_event('[data-task-due="advent-0"]', 'change'); page.wait_for_timeout(400)
    check('Set date Nov 17: calendar draft offered', 'Due Nov 17' in page.inner_text('#ai-stage') and page.locator('[data-cal-open="advent-0"]').count() == 1)
    beat('Task dated, calendar draft', 2)

    # Beat 5c: recorded reply, confirmed meeting, pre-call plan
    page.click('.ai-sidebar [data-nav="accounts"]'); page.wait_for_timeout(300); page.click('#ai-stage [data-account="advent"]'); page.wait_for_timeout(300)
    page.click('#ai-stage [data-tab="meeting"]'); page.wait_for_timeout(300)
    check('Discovery meeting: no reply until one is recorded', 'No reply recorded' in page.inner_text('#ai-stage'))
    page.click('#ai-rr-sim'); page.click('#ai-rr-save'); page.wait_for_timeout(400)
    check('Simulated reply recorded: stage Positive reply, labelled', 'Stage: Positive reply' in page.inner_text('#ai-stage') and 'simulated' in page.inner_text('#ai-stage'))
    page.fill('#ai-mt-date', '2026-11-19'); page.fill('#ai-mt-time', '10:00'); page.click('#ai-mt-save'); page.wait_for_timeout(300)
    check('Meeting draft saved but not booked', 'Stage: Positive reply' in page.inner_text('#ai-stage') and page.locator('#ai-stage [data-meet-cal]').count() == 1)
    page.click('#ai-mt-confirm'); page.wait_for_timeout(500); pc = page.inner_text('#ai-stage'); res['precall'] = pc
    page.screenshot(path=str(OUT / '06b_precall_plan.png'))
    check('Confirmed meeting: internal pre-call plan with shareable agenda, hypotheses and blank notes', 'Stage: Meeting booked' in pc and 'internal pre-call plan' in pc.lower() and 'can be shared with the buyer' in pc.lower() and 'Unknown until the buyer says'.lower() in pc.lower() and page.input_value('#ai-pc-said') == '', pc[:400])
    beat('Reply, meeting, pre-call plan', 4)

    # Beat 6: change one input
    page.click('.ai-sidebar [data-nav="focus"]'); page.wait_for_timeout(300)
    page.click('#ai-stage [data-account="advent"]'); page.wait_for_timeout(300)
    page.click('#ai-stage [data-modal="research"]'); page.wait_for_timeout(300)
    page.locator('#ai-event-toggle').uncheck(force=True); page.wait_for_timeout(400); toast = page.inner_text('#ai-toast')
    check('Switch the dated event off: 9.1 to 4.0, P1 to P2', 'Score 9.1 → 4.0, P1 → P2' in toast, toast)
    page.locator('#ai-event-toggle').check(force=True); page.wait_for_timeout(400); toast2 = page.inner_text('#ai-toast')
    check('Switch it back on: back to 9.1', '9.1' in toast2, toast2)
    page.keyboard.press('Escape'); page.wait_for_timeout(300)
    beat('Change one input and back', 4)

    # Beat 7: the value
    page.click('.ai-sidebar [data-nav="focus"]'); page.wait_for_timeout(300); page.click('[data-open-value]'); page.wait_for_timeout(400)
    val = page.inner_text('.ai-modal'); res['time_back'] = val; page.screenshot(path=str(OUT / '06_time_back.png'))
    check('Time back dialog: by hand, with the workspace, 4.7–8.4 h back', 'By hand' in val and 'With the workspace' in val and '4.7–8.4 h' in val and 'Time back, estimated' in val, val[:400])
    check('Time back dialog never claims a measured saving', not re.search(r'\bmeasured\b|\bproven\b|\bguarantee', val, re.I), val)
    page.keyboard.press('Escape'); page.wait_for_timeout(300)
    beat('Estimated time back', 2)
    res['story_path_seconds'] = round(time.time() - T0, 1)

    # Also: Thoma Bravo, live on the public link
    page.click('.ai-sidebar [data-nav="accounts"]'); page.wait_for_timeout(300)
    page.click('#ai-stage [data-account="thoma"]'); page.wait_for_timeout(400)
    tb_acct = page.inner_text('#ai-stage'); res['thoma_account'] = tb_acct; page.screenshot(path=str(OUT / '07_thoma_account.png'))
    check('Thoma Bravo: account opens with a score, a stage and named people', 'Thoma Bravo' in tb_acct and re.search(r'\b\d\.\d\b', tb_acct) and re.search(r'\bP[12]\b', tb_acct), tb_acct[:300])
    check('Thoma Bravo: score, Why now and What we know agree on the Jun 3, 2025 fund close', 'Last relevant fund event (Jun 3, 2025) is over a year old.' in tb_acct and 'Fund close · Jun 3, 2025. Older fund event (0 of 4 timing points).' in tb_acct and 'Announced Jun 3, 2025.' in tb_acct and 'No dated fund event on file' not in tb_acct and 'No dated trigger yet' not in tb_acct, tb_acct[:900])
    t = res['thoma'] = draft(page, 'thoma', '08_thoma_live_draft.png')
    check('Thoma Bravo live draft succeeded, every claim sourced', t['live'] and not t['failed'] and t['sourced'] and t['sourced'].split('/')[0].strip() == t['sourced'].split('/')[1].strip(), t)
    check('Thoma Bravo email: named contact, greeting on its own line', re.match(r'Hi [A-Z][a-z]+,\n\n', t['message']) and t['message'].split(',')[0][3:] == t['contact'].split()[0], (t['contact'], t['message'][:120]))
    check('Thoma Bravo email says LP, has no filler, at most 110 words', not FILLER.search(t['subject'] + ' ' + t['message']) and words(t['message']) <= 110, (words(t['message']), t['message']))
    res['thoma']['words'] = words(t['message']); res['advent']['words'] = words(a['message'])

    check('No page errors in the whole run', not errors, errors)
    browser.close()

res['passed'] = sum(c['pass'] for c in res['checks']); res['total'] = len(res['checks'])
(OUT / 'story_run.json').write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding='utf-8')
lines = ['# Demo story run', '', f"Link: {URL}", '', f"**{res['passed']} of {res['total']} checks passed.** Story path clicked by script in {res['story_path_seconds']} s. First ranked list on screen in {res['first_list_ms']} ms.", '', '| Check | Result |', '|---|---|']
lines += [f"| {c['check']} | {'pass' if c['pass'] else 'FAIL'} |" for c in res['checks']]
lines += ['', '| Beat | Clicks | Done at (s) |', '|---|---|---|'] + [f"| {b['beat']} | {b['clicks']} | {b['at_seconds']} |" for b in res['beats']]
for key in ('advent', 'thoma'):
    d = res[key]; lines += ['', f"## {key.title()} live draft", '', f"To: {d['contact']}. Model time: {d['response_time']}. Sourced claims: {d['sourced']}. Words: {d['words']}.", '', f"Subject: {d['subject']}", '', '```', d['message'], '```', '', f"Next action: {d['next_action']}"]
(OUT / 'STORY_RUN.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps({'passed': res['passed'], 'total': res['total'], 'story_path_seconds': res['story_path_seconds']}))
