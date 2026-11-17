"""Acceptance walkthrough on the deployed link, in a fresh browser session, with REAL AI drafts (3 calls).
Usage: python scripts/public_walkthrough.py [url] [out_dir]
Writes screenshots and walkthrough.json; prints a short evidence summary."""
import json, re, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = (sys.argv[1] if len(sys.argv) > 1 else 'https://account-intel-live.vercel.app').rstrip('/') + '/'
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else 'docs/public_walkthrough'); OUT.mkdir(parents=True, exist_ok=True)
EDIT = 'Email Heather today: ask how side letter obligations from GPE XI are tracked, and who owns them.'
res = {'url': URL, 'checks': []}
def check(label, ok, detail=''):
    res['checks'].append({'check': label, 'pass': bool(ok), 'detail': str(detail)[:400]}); print(('PASS ' if ok else 'FAIL ') + label + ('' if ok else ' :: ' + str(detail)[:300]))

def draft(page, account, shot):
    """Open an account, run a live draft, return what the seller sees."""
    page.click('.ai-sidebar [data-nav="accounts"]'); page.wait_for_timeout(300)
    page.click(f'#ai-stage [data-account="{account}"]'); page.wait_for_timeout(400)
    t0 = time.time(); page.click('#ai-stage [data-build-plan]')
    page.locator('#ai-plan-action').wait_for(state='visible', timeout=90000)
    wall = round(time.time() - t0, 1); page.wait_for_timeout(400)
    body = page.inner_text('#ai-stage')
    out = {'wall_seconds': wall, 'subject': page.input_value('#ai-message-subject'), 'message': page.input_value('#ai-message'),
           'next_action': page.input_value('#ai-plan-action'), 'hypothesis': page.input_value('#ai-hypothesis'),
           'live': 'AI draft · run summary' in body, 'failed': 'AI draft failed' in body,
           'contact': page.inner_text('#ai-stage .ai-entry strong')}
    for key, label in (('response_time', 'Response time'), ('sourced', 'Sourced claims'), ('inputs', 'Inputs'), ('unknowns', 'Unknowns kept')):
        loc = page.locator(f'#ai-stage .ai-runmetrics div:has(small:text-is("{label}")) strong')
        out[key] = loc.first.inner_text() if loc.count() else None
    out['checks_shown'] = page.locator('#ai-stage .ai-checks li').all_inner_texts()
    out['model_fields'] = page.evaluate("() => [...document.querySelectorAll('#ai-stage .ai-modelfields li')].map(li => ({label: li.querySelector('strong')?.textContent, text: li.querySelector('p')?.textContent, cites: [...li.querySelectorAll('.ai-cite')].map(b => b.textContent)}))")
    page.screenshot(path=str(OUT / shot), full_page=True)
    return out

with sync_playwright() as pw:
    browser = pw.chromium.launch(); ctx = browser.new_context(viewport={'width': 1440, 'height': 900}); page = ctx.new_page()
    errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(URL); page.wait_for_timeout(1500)
    check('Fresh session: top bar shows live AI', 'Live AI' in page.inner_text('.ai-topbar'), page.inner_text('.ai-topbar')[:120])

    # ---------------- Advent
    page.click('.ai-sidebar [data-nav="focus"]'); page.wait_for_timeout(300)
    page.click('#ai-stage [data-account="advent"]'); page.wait_for_timeout(400)
    hot = page.inner_text('#ai-stage .ai-whyhot'); page.screenshot(path=str(OUT / '01_advent_why_hot.png'))
    res['advent_why_hot'] = hot
    check('Advent Why hot: public fundraise and simulated activity are separately labeled', 'Public source' in hot and 'Simulated activity' in hot and '$30 billion' in hot and 'Strongest buyer signal' in hot, hot[:300])
    page.locator('#ai-stage .ai-whyhot .ai-cite.sim').first.click(); page.wait_for_timeout(300)
    ev = page.inner_text('.ai-modal'); res['advent_activity_evidence'] = ev
    check('Advent: simulated evidence opens with its label and no prior contact', 'Simulated data' in ev and 'not contacted this account yet' in ev, ev[:300])
    page.keyboard.press('Escape'); page.wait_for_timeout(200)
    res['advent'] = a = draft(page, 'advent', '02_advent_campaign.png')
    check('Advent live draft: named-contact email, first outreach with no invented call, meeting or tracking', a['live'] and a['message'].startswith('Hi Heather,') and a['contact'].startswith('Heather Zuzenak') and not re.search(r'thanks for the call|our call|pre-read|walkthrough|nov 19|viewed|visited|looked at|opened', a['subject'] + ' ' + a['message'], re.I), a)
    check('Advent: every claim cites a source', a['sourced'] and a['sourced'].split('/')[0].strip() == a['sourced'].split('/')[1].strip(), a['sourced'])
    page.fill('#ai-plan-action', EDIT); page.click('#ai-approve-plan'); page.wait_for_timeout(500)
    page.reload(); page.wait_for_timeout(1500); page.click('.ai-sidebar [data-nav="focus"]'); page.wait_for_timeout(400)
    focus = page.inner_text('#ai-stage'); page.screenshot(path=str(OUT / '03_my_focus_after_approval_and_refresh.png'))
    check('Advent: after approve and refresh, My focus shows the exact edited task', EDIT in focus and 'Approved' in focus, focus[:400])
    page.click('.ai-sidebar [data-nav="tasks"]'); page.wait_for_timeout(300); tasks = page.inner_text('#ai-stage')
    check('Advent: the edited task is in My tasks', EDIT in tasks, tasks[:300])
    page.click('.ai-sidebar [data-nav="focus"]'); page.click('#ai-stage [data-catchup]'); page.click('[data-catch-run]'); page.locator('.ai-weekplan').wait_for(timeout=5000)
    cu = page.inner_text('.ai-modal'); res['plan_for_the_week'] = page.inner_text('.ai-modal .ai-weekplan'); page.screenshot(path=str(OUT / '08_plan_for_the_week.png'))
    check('Advent: catch-me-up no longer says to build the plan', 'build and approve the Advent' not in cu and EDIT in cu, cu[:400])
    wk = page.locator('.ai-modal .ai-weekplan > li')
    check('Plan for the week: five accounts at once with people and titles, no one-per-day rota', wk.count() == 5 and 'Work all five accounts every day' in cu and 'Heather Zuzenak, Chief Compliance Officer' in cu and 'Lizette Perez-Deisboeck, General Counsel and Chief Compliance Officer' in cu and not re.search(r'(?im)^\s*(mon|tue|wed|thu|fri)\s*$', cu), cu[:500])
    page.keyboard.press('Escape'); page.wait_for_timeout(200)
    page.click('[data-open-value]'); tb = page.inner_text('.ai-modal'); res['time_back_after_live'] = tb[-260:]
    check('Time back shows the live run after a live draft', 'Your last AI draft' in tb, tb[-260:]); page.keyboard.press('Escape'); page.wait_for_timeout(200)

    # ---------------- Francisco
    page.click('.ai-sidebar [data-nav="accounts"]'); page.wait_for_timeout(300)
    rows = page.evaluate("() => [...document.querySelectorAll('#ai-stage .ai-queuerow')].map(x => x.innerText.replace(/\\n+/g, ' | '))"); res['account_rows'] = rows
    fp_row = next(x for x in rows if 'Francisco' in x)
    page.click('#ai-stage [data-account="francisco"]'); page.wait_for_timeout(400)
    fp = page.inner_text('#ai-stage'); page.screenshot(path=str(OUT / '04_francisco_account.png'), full_page=True)
    drivers = page.evaluate("() => [...document.querySelectorAll('#ai-stage .ai-scorecard li')].map(li => li.innerText.replace(/\\n+/g, ' | '))"); res['francisco_drivers'] = drivers
    res['francisco_row'] = fp_row
    check('Francisco: list row, score, Why now and What we know agree on the Jul 23 fund close', 'Jul 23' in fp_row and 'Fund close' in fp_row and 'Fund close · Jul 23' in fp and 'Fund event Jul 23, 2026' in fp and '$21 billion' in fp and 'October fundraise' not in fp, fp_row)
    check('Francisco: cooling event shows its credit', '2.8 of 4 timing points' in fp and 'Credit fades evenly' in fp)
    check('Francisco: named, sourced contacts earn full buyer-access credit', 'Steve Eisner, named and sourced (1)' in fp, drivers)
    page.click('.ai-sidebar [data-nav="accounts"]'); page.click('#ai-stage [data-account="gtcr"]'); page.wait_for_timeout(400)
    g = page.evaluate("() => [...document.querySelectorAll('#ai-stage .ai-scorecard li')].map(li => li.innerText.replace(/\\n+/g, ' | '))"); res['gtcr_drivers'] = g
    check('GTCR: role-only credit where the holder needs re-confirming', any('Jeff Wright, role to re-confirm (0.5)' in x for x in g), g)

    # ---------------- HGGC
    page.click('.ai-sidebar [data-nav="accounts"]'); page.click('#ai-stage [data-account="hggc"]'); page.wait_for_timeout(400)
    page.click('#ai-stage h2 .ai-simtag'); page.wait_for_timeout(300); hev = page.inner_text('.ai-modal'); res['hggc_health_evidence'] = hev
    page.screenshot(path=str(OUT / '05_hggc_health_evidence.png'))
    check('HGGC: health label opens the record with numbers and the simulated label', 'Simulated data' in hev and '22 to 11' in hev and '2.8 of 5' in hev, hev[:300])
    page.keyboard.press('Escape'); page.wait_for_timeout(200)
    res['hggc'] = hg = draft(page, 'hggc', '06_hggc_campaign.png')
    blob = json.dumps(hg).lower()
    check('HGGC live draft: no internal or demo wording anywhere', hg['live'] and not any(w in blob for w in ('fictional', 'illustrative', 'demo hold', 'scenario', 'policy', 'the server')), [w for w in ('fictional', 'illustrative', 'demo hold', 'scenario', 'policy', 'the server') if w in blob])
    check('HGGC email: service recovery to a named customer contact, no pitch', hg['message'].startswith('Hi ') and not hg['message'].startswith('Hi there') and any(w in hg['message'].lower() for w in ('delay', 'ticket', 'issue')) and not any(w in hg['message'].lower() for w in ('expand', 'additional funds', 'upgrade', 'new scope')), hg['message'])
    check('HGGC next action: fix first, before expansion', 'retention play' in hg['next_action'].lower() or 'fix' in hg['next_action'].lower(), hg['next_action'])
    cite = page.locator('#ai-stage p.ai-citerow .ai-cite.sim')
    if cite.count():
        cite.first.click(); page.wait_for_timeout(300); cev = page.inner_text('.ai-modal'); page.keyboard.press('Escape')
        check('HGGC: the cited usage claim opens its evidence', 'Simulated data' in cev and '22 to 11' in cev, cev[:200])
    else:
        check('HGGC: the cited usage claim opens its evidence', False, 'no simulated citation under the hypothesis')

    # ---------------- TA
    res['ta'] = ta = draft(page, 'ta', '07_ta_campaign.png')
    tblob = json.dumps(ta).lower()
    check('TA live draft uses TA-specific evidence (2 remaining funds, rising usage)', ta['live'] and ('2 remaining funds' in tblob or '2 funds' in tblob or 'two' in tblob) and ('18 to 26' in tblob or 'quarterly review' in tblob), ta['message'])
    check('TA email answers the customer request; HGGC and TA emails differ', ta['message'] != hg['message'] and ('fund' in ta['message'].lower()), ta['message'])
    check('No page errors during the walkthrough', not errors, errors[:3])
    browser.close()

res['passed'] = sum(c['pass'] for c in res['checks']); res['total'] = len(res['checks'])
(OUT / 'walkthrough.json').write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps({'passed': res['passed'], 'total': res['total'], 'out': str(OUT)}))
