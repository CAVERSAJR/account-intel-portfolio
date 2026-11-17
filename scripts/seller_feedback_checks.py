"""Checks for the seller-feedback patch: profile links, boxed sections, phone layout, task due date + Google Calendar handoff,
Print / Save PDF report. No model call (/api/status forced off, so plans use the prepared draft).
Usage: python scripts/seller_feedback_checks.py [url] [out_dir]"""
import json, sys, re, pathlib
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8767/'
out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else 'docs/seller_feedback'); out.mkdir(parents=True, exist_ok=True)
EDIT = 'Send Heather the pre-read by Wednesday and confirm Brian is joining Thursday.'
checks = []
def check(label, ok, detail=''):
    checks.append({'label': label, 'ok': bool(ok), 'detail': '' if ok else str(detail)[:400]})
    print(('PASS ' if ok else 'FAIL ') + label + ('' if ok else '  ::  ' + str(detail)[:300]))

def open_handover(p):
    p.click('#ai-stage [data-catchup]'); p.wait_for_timeout(300)
    p.click('[data-catch-run]'); p.locator('.ai-catchsection').first.wait_for(timeout=5000); p.wait_for_timeout(900)

with sync_playwright() as pw:
    b = pw.chromium.launch()
    # ---------- desktop ----------
    ctx = b.new_context(viewport={'width': 1440, 'height': 900})
    ctx.add_init_script("window.__printed=0; window.print=()=>{window.__printed++;};")
    p = ctx.new_page(); errs = []
    p.on('pageerror', lambda e: errs.append(str(e)))
    p.route('**/api/status', lambda r: r.fulfill(status=404, body='off'))
    p.goto(url); p.wait_for_selector('#ai-stage'); p.wait_for_timeout(700)
    open_handover(p)
    secs = p.evaluate("""() => [...document.querySelectorAll('.ai-modal .ai-catchsection')].map(s => ({cls: s.className, h: s.querySelector('h3').innerText.trim(), icon: !!s.querySelector('h3 svg'), border: getComputedStyle(s).borderLeftWidth, bg: getComputedStyle(s).backgroundImage !== 'none'}))""")
    check('Handover: four sections, each boxed with a 5px colored edge, icon and label', len(secs) == 4 and all(s['border'] == '5px' and s['icon'] for s in secs) and [s['h'] for s in secs] == ['Start here', 'Defend the house', 'Gaps to close', 'Plan for the week'], secs)
    links = p.evaluate("""() => [...document.querySelectorAll('.ai-modal a.ai-proflink')].map(a => ({href: a.href, target: a.target, rel: a.rel, text: a.innerText.trim(), sec: a.closest('.ai-catchsection').querySelector('h3').innerText.trim()}))""")
    start = [l for l in links if l['sec'] == 'Start here']; plan = [l for l in links if l['sec'] == 'Plan for the week']
    check('Start here: a firm-profile link for each of the top three entry points', len(start) == 3, start)
    npeople = p.locator('.ai-modal .ai-cs-plan .ai-weekpeople li').count()
    check(f'Plan for the week: a firm-profile link for every named person ({npeople})', npeople >= 10 and len(plan) == npeople, (len(plan), npeople))
    check('Every profile link is https, opens a new tab with noopener, and is not LinkedIn', links and all(l['href'].startswith('https://') and l['target'] == '_blank' and 'noopener' in l['rel'] and 'linkedin' not in l['href'] for l in links), links[:3])
    heather = [l for l in start if 'heather-zuzenak' in l['href']]
    check('Advent entry point links to Heather Zuzenak on adventinternational.com', heather and urlparse(heather[0]['href']).netloc.endswith('adventinternational.com'), start[:1])
    p.locator('.ai-modal').first.screenshot(path=str(out / '01_handover_desktop.png'))
    check('Print / Save PDF button on the handover brief', p.locator('.ai-modal [data-print-report]').count() == 1)
    p.keyboard.press('Escape'); p.wait_for_timeout(300)

    # approve Advent with the seller's edit
    p.click('#ai-stage [data-account="advent"]'); p.wait_for_timeout(400)
    p.click('#ai-stage [data-build-plan]'); p.locator('#ai-plan-action').wait_for(state='visible', timeout=40000)
    p.fill('#ai-plan-action', EDIT); p.click('#ai-approve-plan'); p.wait_for_timeout(700)
    p.click('.ai-sidebar [data-nav="tasks"]'); p.wait_for_timeout(500)
    rows = p.locator('#ai-stage .ai-task')
    check('My tasks: approval created three Advent tasks', rows.count() == 3, rows.count())
    first = rows.nth(0)
    check('First task is the exact edited next action', EDIT in first.inner_text(), first.inner_text()[:200])
    check('Task checkbox still has a label (clicking the text toggles it)', p.evaluate("() => { const i = document.querySelector('#ai-stage .ai-task input[type=checkbox]'); return !!(i && i.labels && i.labels.length); }"))
    tx = p.inner_text('#ai-stage')
    check('No date is stamped on approval: the two dated-style tasks say No date yet', tx.count('No date yet') == 2 and 'Due Nov 16' not in tx and 'Due Nov 17' not in tx, tx[:400])
    check('No calendar button until the seller picks a date', p.locator('#ai-stage [data-cal-open]').count() == 0 and p.locator('#ai-stage [data-task-due]').count() == 2)
    check('Open Google Calendar link in the My tasks header', p.locator('#ai-stage a[href^="https://calendar.google.com/calendar/r/week/2026/11/16"]').count() == 1)
    p.fill('[data-task-due="advent-0"]', '2026-11-18'); p.dispatch_event('[data-task-due="advent-0"]', 'change'); p.wait_for_timeout(500)
    t0 = p.locator('#ai-stage .ai-task').nth(0).inner_text()
    check('Seller sets the due date: task shows Due Nov 18', 'Due Nov 18' in t0, t0[:300])
    check('Calendar button appears only on the task the seller dated', p.locator('#ai-stage [data-cal-open]').count() == 1 and p.locator('#ai-stage [data-cal-open="advent-0"]').count() == 1)
    href = p.locator('#ai-stage [data-cal-open="advent-0"]').get_attribute('href')
    u = urlparse(href); q = parse_qs(u.query)
    check('Calendar link: Google Calendar new-event screen', u.netloc == 'calendar.google.com' and u.path == '/calendar/render' and q.get('action') == ['TEMPLATE'], href)
    check('Calendar link: all-day on Nov 18, Los Angeles time zone', q.get('dates') == ['20261118/20261119'] and q.get('ctz') == ['America/Los_Angeles'], q)
    check('Calendar link: title has the account and the exact action', q.get('text') == ['Advent International: ' + EDIT], q.get('text'))
    check('Calendar link: no guests, no email, nothing sent', 'add' not in q and '@' not in href and 'nothing was sent' in (q.get('details') or [''])[0], q.keys())
    with ctx.expect_page(timeout=10000) as pop:
        p.click('#ai-stage [data-cal-open="advent-0"]')
    newp = pop.value; dest = newp.url; newp.close()
    check('Clicking it opens a new tab on calendar.google.com', 'calendar.google.com' in dest or 'accounts.google.com' in dest, dest)
    toast = p.inner_text('#ai-toast')
    check('Toast says opened, not scheduled', 'Opened in Google Calendar' in toast and 'Scheduled' not in toast, toast)
    p.locator('#ai-stage').screenshot(path=str(out / '02_tasks_desktop.png'))

    # persistence + re-approval keep the chosen date
    p.reload(); p.wait_for_selector('#ai-stage'); p.wait_for_timeout(700)
    p.click('.ai-sidebar [data-nav="tasks"]'); p.wait_for_timeout(400)
    check('After a reload the task still says Due Nov 18', 'Due Nov 18' in p.locator('#ai-stage .ai-task').nth(0).inner_text())
    p.click('.ai-sidebar [data-nav="accounts"]'); p.wait_for_timeout(300); p.click('#ai-stage [data-account="advent"]'); p.wait_for_timeout(400)
    if p.locator('#ai-stage [data-tab="plan"]').count(): p.click('#ai-stage [data-tab="plan"]'); p.wait_for_timeout(400)
    if p.locator('#ai-plan-action').count() and p.locator('#ai-plan-action').is_visible():
        p.fill('#ai-plan-action', EDIT); p.click('#ai-approve-plan'); p.wait_for_timeout(500)
        p.click('.ai-sidebar [data-nav="tasks"]'); p.wait_for_timeout(400)
        check('Reapproving the same action keeps the chosen date', 'Due Nov 18' in p.locator('#ai-stage .ai-task').nth(0).inner_text(), p.locator('#ai-stage .ai-task').nth(0).inner_text()[:200])
    else:
        check('Reapproving the same action keeps the chosen date (plan view not reachable from the record)', False, 'no #ai-plan-action on the Advent record')

    # report
    p.click('.ai-sidebar [data-nav="focus"]'); p.wait_for_timeout(400)
    open_handover(p)
    p.click('.ai-modal [data-print-report]'); p.wait_for_timeout(500)
    check('Print / Save PDF opens the print dialog once', p.evaluate('window.__printed') == 1, p.evaluate('window.__printed'))
    rep = p.evaluate("() => document.getElementById('ai-print') ? document.getElementById('ai-print').innerText : ''")
    names = ['Advent International', 'Francisco Partners', 'Battery Ventures', 'Audax Private Equity', 'GI Partners', 'TA Associates', 'HGGC']
    check('Report: all five top accounts and both customers', all(n in rep for n in names), [n for n in names if n not in rep])
    check('Report: the edited action, marked Approved by you, with Due Nov 18', EDIT in rep and 'Approved by you' in rep and 'Due Nov 18' in rep, rep[:600])
    check('Report: Advent pain and questions come from the approved plan; the others are prepared suggestions', rep.count('(from your approved plan)') == 2 and rep.count('(prepared suggestion)') == 8, (rep.count('(from your approved plan)'), rep.count('(prepared suggestion)')))
    check('Report: Why now links the dated announcement for Advent, Francisco and Battery', all(u in rep for u in ('Source (Oct 27, 2026)', 'Source (Jul 23, 2026)', 'Source (Feb 18, 2026)')) and 'Source' not in rep.split('4. Audax')[1].split('5. GI')[0], '')
    check('Report: research date separate from report date', 'Report prepared Nov 16, 2026' in rep and 'Research as of Nov 12, 2026' in rep, rep[:300])
    check('Report: roles say Potential, never a bare Champion', 'Potential champion' in rep and not re.search(r'\((Champion|Budget owner)\)', rep), '')
    check('Report: other accounts stay Suggested', rep.count('Suggested') >= 4, rep.count('Suggested'))
    check('Report: product focus, discovery questions and profile URLs', 'Product focus: LP obligation tracking' in rep and rep.count('Discovery question') == 5 and 'https://www.adventinternational.com/our-team/heather-zuzenak/' in rep, '')
    check('Report: simulated data labelled, nothing sent', 'simulated' in rep and 'nothing in this plan was sent to a buyer' in rep, '')
    check('Report: no banned words', not re.search(r'(?i)\b(pilot|baseline|modeled|assumption|investor obligation|interview|hack day|fictional|illustrative)\b', rep), re.findall(r'(?i)\b(pilot|baseline|modeled|assumption|investor obligation|interview|hack day|fictional|illustrative)\b', rep))
    toast = p.inner_text('#ai-toast')
    check('Print toast does not claim a PDF was saved', 'saved' not in toast.lower(), toast)
    p.emulate_media(media='print')
    p.pdf(path=str(out / 'Account_Intel_weekly_plan.pdf'), format='Letter', print_background=True)
    vis = p.evaluate("() => [...document.body.children].filter(e => getComputedStyle(e).display !== 'none').map(e => e.id || e.tagName)")
    check('In print, only the report is visible', vis == ['ai-print'], vis)
    p.emulate_media(media='screen')
    p.keyboard.press('Escape'); p.wait_for_timeout(300)

    # weekly brief has the button too
    p.click('#ai-stage [data-brief-kind="weekly"]') if p.locator('#ai-stage [data-brief-kind="weekly"]').count() else None
    p.wait_for_timeout(300)
    for bt in p.locator('button').filter(has_text='Prepare brief').all():
        if bt.is_visible(): bt.click(); break
    p.wait_for_timeout(1200)
    check('Weekly brief preview also has Print / Save PDF', p.locator('.ai-modal [data-print-report]').count() == 1, p.locator('.ai-modal').count())
    p.keyboard.press('Escape'); p.wait_for_timeout(300)

    # evidence change: approval withdrawn, calendar handoff gone
    p.click('.ai-sidebar [data-nav="accounts"]'); p.wait_for_timeout(300)
    p.click('#ai-stage [data-account="advent"]'); p.wait_for_timeout(300)
    p.click('#ai-stage [data-modal="research"]'); p.wait_for_timeout(300)
    p.locator('#ai-event-toggle').uncheck(force=True); p.wait_for_timeout(400)
    tst = p.inner_text('#ai-toast')
    check('Event off still reads 9.1 to 4.0, P1 to P2', 'Score 9.1 → 4.0, P1 → P2' in tst, tst)
    p.locator('#ai-event-toggle').check(force=True); p.wait_for_timeout(400)
    p.keyboard.press('Escape'); p.wait_for_timeout(300)
    p.click('.ai-sidebar [data-nav="tasks"]'); p.wait_for_timeout(400)
    check('After the evidence change the Advent tasks and calendar buttons are gone', p.locator('#ai-stage [data-cal-open]').count() == 0 and EDIT not in p.inner_text('#ai-stage'), p.inner_text('#ai-stage')[:300])
    check('No page errors (desktop)', not errs, errs)
    ctx.close()

    # ---------- phones ----------
    for w in (360, 390, 430):
        ctx = b.new_context(viewport={'width': w, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        p = ctx.new_page(); errs = []
        p.on('pageerror', lambda e: errs.append(str(e)))
        p.route('**/api/status', lambda r: r.fulfill(status=404, body='off'))
        p.goto(url); p.wait_for_selector('#ai-stage'); p.wait_for_timeout(700)
        open_handover(p)
        m = p.evaluate("""() => { const sec = document.querySelector('.ai-modal .ai-catchsection'); const li = sec.querySelector('li');
            const links = [...document.querySelectorAll('.ai-modal a.ai-proflink')];
            return {docW: document.documentElement.scrollWidth, vw: window.innerWidth, h3: getComputedStyle(sec.querySelector('h3')).fontSize, li: getComputedStyle(li).fontSize,
                    linkH: Math.min(...links.map(a => a.getBoundingClientRect().height)), overflow: [...document.querySelectorAll('.ai-modal *')].filter(e => e.getBoundingClientRect().right > window.innerWidth + 1).length,
                    footer: [...document.querySelectorAll('.ai-modalfooter button')].map(x => { const r = x.getBoundingClientRect(); return [x.innerText.trim(), Math.round(r.left), Math.round(r.right)]; })}; }""")
        check(f'{w}px: no sideways scroll and nothing wider than the screen in the brief', m['docW'] <= m['vw'] and m['overflow'] == 0, m)
        check(f'{w}px: section headings 16px, body 15px', m['h3'] == '16px' and m['li'] == '15px', (m['h3'], m['li']))
        check(f'{w}px: profile links at least 32px tall to tap', m['linkH'] >= 32, m['linkH'])
        check(f'{w}px: footer buttons (Print, Prepare again) fit on screen', all(l >= 0 and r <= m['vw'] for _, l, r in m['footer']), m['footer'])
        if w == 390:
            # full-length capture of the brief: scroll the dialog body and stitch nothing, just top + Plan for the week
            p.locator('.ai-modal').first.screenshot(path=str(out / '03_handover_phone390_top.png'))
            p.locator('.ai-cs-plan').scroll_into_view_if_needed(); p.wait_for_timeout(300)
            p.screenshot(path=str(out / '04_handover_phone390_plan.png'))
        p.keyboard.press('Escape'); p.wait_for_timeout(300)
        p.click('#ai-stage [data-account="advent"]'); p.wait_for_timeout(400)
        p.click('#ai-stage [data-build-plan]'); p.locator('#ai-plan-action').wait_for(state='visible', timeout=40000)
        p.click('#ai-approve-plan'); p.wait_for_timeout(600)
        p.click('[data-nav="tasks"]'); p.wait_for_timeout(500)
        p.fill('[data-task-due="advent-0"]', '2026-11-18'); p.dispatch_event('[data-task-due="advent-0"]', 'change'); p.wait_for_timeout(500)
        t = p.evaluate("""() => { const b = document.querySelector('#ai-stage [data-cal-open]'); const r = b.getBoundingClientRect();
            return {docW: document.documentElement.scrollWidth, vw: window.innerWidth, btnH: Math.round(r.height), right: Math.round(r.right)}; }""")
        check(f'{w}px: tasks screen fits, calendar button 44px tall and on screen', t['docW'] <= t['vw'] and t['btnH'] >= 44 and t['right'] <= t['vw'], t)
        if w == 390:
            p.screenshot(path=str(out / '05_tasks_phone390.png'), full_page=True)
        check(f'{w}px: no page errors', not errs, errs)
        ctx.close()
    b.close()

res = {'url': url, 'passed': sum(c['ok'] for c in checks), 'total': len(checks), 'checks': checks}
(out / 'seller_feedback_checks.json').write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding='utf-8')
print(json.dumps({k: res[k] for k in ('url', 'passed', 'total')}))
