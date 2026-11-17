"""Failed regeneration must keep the seller's work. Mocked AI only (no model call): /api/status reports AI connected and
/api/draft is routed to a scripted successful draft or a provider failure.
Covers: failed regenerate after edit + approve; failed regenerate on a plan whose evidence changed (stays stale);
failed first generation (labelled prepared fallback); successful regenerate (existing re-review behaviour).
Usage: python scripts/regen_failure_checks.py [url] [out_dir]"""
import json, sys, pathlib
from playwright.sync_api import sync_playwright
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from simulate_sellers import ADVENT_PLAN, sse_body

url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8767/'
out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else 'docs/regen_repair'); out.mkdir(parents=True, exist_ok=True)
EDIT = 'REHEARSAL CHECK: ask Heather who owns the obligation handoff.'
FAIL_SSE = 'event: start\ndata: {"model": "deepseek-flash", "sources": 12}\n\nevent: error\ndata: ' + json.dumps({'error': 'The model provider is unavailable. The prior plan is unchanged.'}) + '\n\n'
checks = []
def check(label, ok, detail=''):
    checks.append({'label': label, 'ok': bool(ok), 'detail': '' if ok else str(detail)[:400]})
    print(('PASS ' if ok else 'FAIL ') + label + ('' if ok else '  ::  ' + str(detail)[:300]))
def store(p): return p.evaluate("() => JSON.parse(localStorage.getItem('account-intelligence-seller-workflow-v1') || '{}')")
def snapshot(p):
    s = store(p); pl = s.get('plans', {}).get('advent', {})
    return {'action': pl.get('action'), 'approved': pl.get('approved'), 'revision': pl.get('revision'), 'sig': pl.get('sig'), 'ai': (pl.get('ai') or {}).get('status'),
            'tasks': sorted((t['id'], t['text'], t.get('due')) for t in s.get('tasks', []) if t['account'] == 'advent')}

def context(b, mode):
    ctx = b.new_context(viewport={'width': 1440, 'height': 900}); p = ctx.new_page(); errs = []
    p.on('pageerror', lambda e: errs.append(str(e)))
    p.route('**/api/status', lambda r: r.fulfill(status=200, content_type='application/json', body=json.dumps({'configured': True, 'provider': 'deepseek', 'model': 'deepseek-flash'})))
    p.route('**/api/draft', lambda r: r.fulfill(status=200, content_type='text/event-stream', body=sse_body(ADVENT_PLAN) if mode['draft'] == 'ok' else FAIL_SSE))
    p.goto(url); p.wait_for_selector('#ai-stage'); p.wait_for_timeout(700)
    return ctx, p, errs

def build_and_approve(p):
    p.click('#ai-stage [data-account="advent"]'); p.wait_for_timeout(300)
    p.click('#ai-stage [data-build-plan]'); p.locator('#ai-plan-action').wait_for(state='visible', timeout=40000); p.wait_for_timeout(500)
    p.fill('#ai-plan-action', EDIT); p.click('#ai-approve-plan'); p.wait_for_timeout(500)

def regenerate(p):
    btn = p.locator('#ai-stage [data-regenerate-plan]').first
    btn.wait_for(state='visible', timeout=10000); btn.click()
    p.locator('#ai-plan-action').wait_for(state='visible', timeout=40000); p.wait_for_timeout(700)

with sync_playwright() as pw:
    b = pw.chromium.launch()

    # A. edit + approve, then a failed regenerate
    mode = {'draft': 'ok'}; ctx, p, errs = context(b, mode)
    build_and_approve(p)
    before = snapshot(p)
    check('Setup: AI draft approved with the edited action and three tasks', before['approved'] and before['action'] == EDIT and before['ai'] == 'success' and len(before['tasks']) == 3, before)
    mode['draft'] = 'fail'; regenerate(p)
    after = snapshot(p)
    check('Failed regenerate keeps the edited action', after['action'] == EDIT, after['action'])
    check('Failed regenerate keeps approval, revision and review signature', after['approved'] is True and after['revision'] == before['revision'] and after['sig'] == before['sig'], (before, after))
    check('Failed regenerate keeps all three dependent tasks unchanged', after['tasks'] == before['tasks'], (before['tasks'], after['tasks']))
    check('The retained plan is still the AI draft, not a prepared fallback', after['ai'] == 'success' and p.input_value('#ai-plan-action') == EDIT)
    page = p.inner_text('#ai-stage'); toast = p.inner_text('#ai-toast')
    check('The failed attempt is shown separately from the retained plan', 'Regeneration failed' in page and 'previous plan, unchanged, still approved' in page, page[:400])
    check('No outdated-evidence warning when the evidence did not change', 'research changed after this draft' not in page, page[:300])
    check('Messages describe what was kept; no "Nothing was lost"', 'Nothing was lost' not in page and 'Nothing was lost' not in toast and 'unchanged' in toast, toast)
    p.click('.ai-sidebar [data-nav="tasks"]'); p.wait_for_timeout(300)
    check('My tasks still shows the edited action', EDIT in p.inner_text('#ai-stage'))
    p.screenshot(path=str(out / 'failed_regenerate_kept.png'))
    check('No page errors (A)', not errs, errs); ctx.close()

    # B. evidence changed, then a failed regenerate: plan must stay flagged as outdated
    mode = {'draft': 'ok'}; ctx, p, errs = context(b, mode)
    build_and_approve(p)
    p.click('#ai-stage [data-account="advent"]') if p.locator('#ai-stage [data-account="advent"]').count() else None
    p.click('.ai-sidebar [data-nav="accounts"]'); p.wait_for_timeout(300); p.click('#ai-stage [data-account="advent"]'); p.wait_for_timeout(300)
    p.click('#ai-stage [data-modal="research"]'); p.wait_for_timeout(300)
    p.locator('#ai-event-toggle').uncheck(force=True); p.wait_for_timeout(400); p.keyboard.press('Escape'); p.wait_for_timeout(300)
    stale_before = snapshot(p)
    p.click('#ai-stage [data-build-plan]'); p.locator('#ai-plan-action').wait_for(state='visible', timeout=20000); p.wait_for_timeout(300)
    check('Setup: changed evidence shows the outdated-plan warning', 'research changed after this draft' in p.inner_text('#ai-stage'))
    mode['draft'] = 'fail'; regenerate(p)
    stale_after = snapshot(p)
    cur_sig = p.evaluate("() => window.AccountIntelEngine.signature('advent')")
    check('Failed regenerate does not make the outdated plan current', stale_after['sig'] == stale_before['sig'] and stale_after['sig'] != cur_sig and stale_after['approved'] is False, (stale_after, cur_sig))
    check('The outdated-plan warning is still shown after the failed attempt', 'research changed after this draft' in p.inner_text('#ai-stage') and 'Regeneration failed' in p.inner_text('#ai-stage'))
    check('Failed regenerate keeps the edited action on the outdated plan', stale_after['action'] == EDIT, stale_after['action'])
    check('No page errors (B)', not errs, errs); ctx.close()

    # C. failed first generation: labelled prepared fallback
    mode = {'draft': 'fail'}; ctx, p, errs = context(b, mode)
    p.click('#ai-stage [data-account="advent"]'); p.wait_for_timeout(300)
    p.click('#ai-stage [data-build-plan]'); p.locator('#ai-plan-action').wait_for(state='visible', timeout=40000); p.wait_for_timeout(500)
    first = snapshot(p); page = p.inner_text('#ai-stage'); toast = p.inner_text('#ai-toast')
    check('Failed first generation shows a labelled prepared draft', first['ai'] == 'failed' and 'Prepared draft' in page and 'This is a prepared draft, not an AI result' in page, page[:300])
    check('Failed first generation is not approved and creates no tasks', first['approved'] is False and first['tasks'] == [], first)
    check('Failed first generation messages make no "Nothing was lost" claim', 'Nothing was lost' not in page and 'Nothing was lost' not in toast, toast)
    check('No page errors (C)', not errs, errs); ctx.close()

    # D. successful regenerate keeps the existing re-review behaviour
    mode = {'draft': 'ok'}; ctx, p, errs = context(b, mode)
    build_and_approve(p); before = snapshot(p)
    regenerate(p); after = snapshot(p)
    check('Successful regenerate replaces the draft and asks for review again', after['ai'] == 'success' and after['approved'] is False and after['revision'] == before['revision'] + 1 and after['action'] != EDIT, (before, after))
    check('Successful regenerate removes the old plan tasks until re-approval', after['tasks'] == [], after['tasks'])
    check('Successful regenerate shows no failed-attempt banner', 'Regeneration failed' not in p.inner_text('#ai-stage'))
    check('No page errors (D)', not errs, errs); ctx.close()
    b.close()

res = {'url': url, 'passed': sum(c['ok'] for c in checks), 'total': len(checks), 'checks': checks}
(out / 'regen_failure_checks.json').write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding='utf-8')
print(json.dumps({k: res[k] for k in ('url', 'passed', 'total')}))
