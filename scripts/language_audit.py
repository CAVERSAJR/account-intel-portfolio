"""Release wording audit for the seller workspace.

Walks every screen, every account, every tab and every dialog in a real browser with
AI switched off (so the text is the same on every run), collects the visible text plus
tooltips, labels, placeholders and form values, and fails on any wording rule below.
Also checks each screen for page errors and sideways scrolling at desktop and phone width.

Usage:
  python scripts/language_audit.py --url http://127.0.0.1:8767/ --out docs/language_audit
"""
from __future__ import annotations
import argparse, json, re, sys
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
from simulate_sellers import BANNED  # the former-employer, vendor and analyst-voice list already in use

RULES = [
    ('Filler or sales cliche', re.compile(r"\b(i imagine|i hope|reach(?:ing|ed)? out|touch(?:ing)? base|circl(?:e|ing) back|delv(?:e|es|ing)|seamless(?:ly)?|unlock(?:s|ed|ing)?|empower(?:s|ed|ing)?|robust|streamlin(?:e|es|ed|ing)|game-chang\w*|cutting-edge|supercharg\w*|holistic|synerg\w*|bespoke|best-in-class|world-class|pain points?|excited to|thrilled|revolutioni[sz]\w*|in today's|ever-evolving|fast-paced|tapestry|testament to|elevate|effortless\w*|actionable|at the end of the day|low-hanging|move the needle|deep dive|leverag(?:e|es|ing)\b(?! buyout))", re.I)),
    ('Wrong term for LP obligations', re.compile(r'investor[- ]obligations?|investor-specific|investor commitments?', re.I)),
    ('Raw ISO date', re.compile(r'\b20\d\d-\d\d-\d\d\b')),
    ('Em dash', re.compile('—')),
    ('Spaced en dash outside a date or number range', re.compile(r'(?<![0-9]) – (?![0-9A-Z])')),
    ('Broken value on screen', re.compile(r'\bundefined\b|\bNaN\b|\[object |\$\{|\bnull\b(?! and void)')),
    ('Double space or stray punctuation', re.compile(r'[A-Za-z,.;:]  +[A-Za-z]|\s[,;:](?=\s|$)|,,|(?<![.0-9])\.\.(?!\.)|\s\.(?=\s|$)|!')),
    ('Email address or LinkedIn link', re.compile(r'[\w.+-]+@[\w-]+\.[a-z]{2,}|linkedin\.com', re.I)),
    ('Engineer wording', re.compile(r'\blive model\b|\bLLM\b|\bprompt\b|\bJSON\b|\bAPI\b|\bendpoint\b|\btoken(?:s)?\b(?! of)', re.I)),
    ('Off-vocabulary word', re.compile(r'\bremit\b|\bgrowth (?:talk|conversation)\b|\bblocks growth\b|\bsave plan\b|\bside-letter\b|\bupsell\b|\bchurn\b', re.I)),
    ('British spelling', re.compile(r'\b\w+(?:ising|isation|ised)\b|\bcolour|\bfavour|\bwhilst\b|\bprogramme\b|\bcentre\b|\blicence\b', re.I)),
]
# Words that look like a rule hit but are correct here.
ALLOW = re.compile(r'\b(?:advised|supervised|revised|raised|promised|surprised|exercised|comprised|praised|franchised|disguised|televised|improvised|merchandising|advertising|raising|rising|arising|promising|surprising|advising|supervising|exercising|comprising|revising|fundraising)\b', re.I)
# The AI run summary shows the model call on purpose: response time, tokens in and out, sources sent.
TOKENS_OK = re.compile(r'Times and tokens are from that run|one model call Tokens \d', re.I)


def lint(label: str, text: str):
    hits = []
    for name, rx in RULES:
        for m in rx.finditer(text):
            word = m.group(0)
            if name == 'British spelling' and ALLOW.fullmatch(word): continue
            start = max(0, m.start() - 50); snippet = re.sub(r'\s+', ' ', text[start:m.end() + 50]).strip()
            if name == 'Engineer wording' and TOKENS_OK.search(snippet): continue
            hits.append({'screen': label, 'rule': name, 'match': word.strip(), 'context': snippet})
    low = text.lower()
    for w in BANNED:
        if w in low:
            i = low.index(w); hits.append({'screen': label, 'rule': 'Banned name or analyst voice', 'match': w, 'context': re.sub(r'\s+', ' ', text[max(0, i - 50):i + len(w) + 50]).strip()})
    return hits


GRAB = """(sel) => { const root = document.querySelector(sel); if (!root) return null;
  const attrs = [...root.querySelectorAll('[title],[aria-label],[placeholder]')].flatMap(e => [e.getAttribute('title'), e.getAttribute('aria-label'), e.getAttribute('placeholder')]).filter(Boolean);
  const vals = [...root.querySelectorAll('textarea,input[type=text],input:not([type]),select')].map(e => e.tagName === 'SELECT' ? [...e.options].map(o => o.text).join(' | ') : e.value).filter(Boolean);
  return root.innerText + '\\n[labels]\\n' + [...new Set(attrs)].join('\\n') + '\\n[values]\\n' + vals.join('\\n---\\n'); }"""


def run(url: str, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    screens, findings, walker_errors, page_errors, overflow = [], [], [], [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for width, height in ((1366, 900), (390, 844)):
            ctx = b.new_context(viewport={'width': width, 'height': height}); pg = ctx.new_page()
            pg.on('pageerror', lambda e: page_errors.append(str(e)))
            pg.on('console', lambda m: page_errors.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
            pg.route('**/api/**', lambda r: r.fulfill(status=404, body=''))
            pg.goto(url); pg.wait_for_timeout(1200)
            phone = width < 700

            def grab(label):
                pg.wait_for_timeout(300)
                sel = '.ai-modal' if pg.locator('.ai-modal').count() else ('#ai-tour' if pg.locator('#ai-tour').count() and pg.locator('#ai-tour').is_visible() else '#account-intelligence-refined')
                text = pg.evaluate(GRAB, sel) or ''
                toast = pg.locator('#ai-toast'); text += ('\n[toast]\n' + toast.inner_text()) if toast.count() and toast.is_visible() else ''
                name = f'{label} @{width}'
                screens.append({'screen': name, 'chars': len(text), 'text': text}); findings.extend(lint(name, text))
                sw = pg.evaluate('document.documentElement.scrollWidth')
                if sw > width + 1: overflow.append({'screen': name, 'scrollWidth': sw, 'viewport': width})

            def step(label, fn):
                try: fn()
                except Exception as e:  # a screen the walker could not reach is a failure, not a skip
                    walker_errors.append({'screen': f'{label} @{width}', 'error': str(e).split('\n')[0][:200]})
                    try: pg.keyboard.press('Escape')
                    except Exception: pass

            def esc(): pg.keyboard.press('Escape'); pg.wait_for_timeout(250)
            def nav(n):
                if pg.locator('.ai-modal').count(): esc()
                pg.locator(f'[data-nav="{n}"]').locator('visible=true').first.click(); pg.wait_for_timeout(350)
            def open_all(): pg.locator('#ai-stage details').evaluate_all('els => els.forEach(e => e.open = true)')
            def open_account(a):
                nav('accounts'); pg.locator(f'#ai-stage [data-account="{a}"]').first.click(); pg.wait_for_timeout(350)

            ids = pg.evaluate("() => { document.querySelector('[data-nav=\"accounts\"]'); return null; }")
            step('My focus', lambda: (nav('focus'), open_all(), grab('My focus')))
            step('Accounts', lambda: (nav('accounts'), grab('Accounts')))
            ids = pg.evaluate("() => [...new Set([...document.querySelectorAll('#ai-stage [data-account]')].map(e => e.dataset.account))]")
            def search():
                if not pg.locator('#ai-find').locator('visible=true').count(): return
                pg.locator('#ai-find').locator('visible=true').first.click(); pg.fill('#ai-search-input', 'zzzz'); grab('Search: no result')
                pg.fill('#ai-search-input', 'bat'); grab('Search: one result'); esc()
            step('Search', search)
            step('Tasks, empty', lambda: (nav('tasks'), grab('My tasks: empty')))
            step('Briefs', lambda: (nav('briefs'), grab('Briefs')))
            def weekly():
                nav('briefs'); pg.locator('#ai-stage [data-brief-kind="weekly"]').first.click(); grab('Weekly brief: intro')
                pg.click('#ai-compose-brief'); pg.locator('#ai-save-brief').wait_for(timeout=8000); grab('Weekly brief: prepared'); pg.click('#ai-save-brief'); grab('Weekly brief: saved')
            step('Weekly brief', weekly)
            def daily():
                nav('briefs'); pg.locator('#ai-stage [data-brief-kind="daily"]').first.click(); grab('Daily brief: intro')
                pg.click('#ai-compose-brief'); pg.locator('#ai-save-brief').wait_for(timeout=8000); grab('Daily brief: prepared'); pg.click('#ai-save-brief'); grab('Daily brief: saved'); nav('briefs'); grab('Briefs: with saved briefs')
            step('Daily brief', daily)
            def catchup():
                nav('focus'); pg.locator('#ai-stage [data-catchup]').first.click(); grab('Catch-up: pick')
                pg.click('[data-catch-run]'); pg.locator('.ai-weekplan').first.wait_for(timeout=8000); grab('Catch-up: handover')
                pg.click('[data-catch-kind="return"]'); grab('Catch-up: return pick')
                for weeks in pg.evaluate("() => [...document.querySelectorAll('[data-leave-weeks]')].map(e => e.dataset.leaveWeeks)"):
                    pg.click(f'[data-leave-weeks="{weeks}"]'); pg.click('[data-catch-run]'); pg.locator('.ai-changelist').first.wait_for(timeout=8000); grab(f'Catch-up: back after {weeks} weeks')
                    if pg.locator('[data-catch-again]').count(): pg.click('[data-catch-again]')
                esc()
            step('Catch-up', catchup)
            step('Time back', lambda: (nav('focus'), pg.locator('[data-open-value]').first.click(), grab('Time back'), esc()))
            def guide():
                nav('focus')
                if phone and not pg.locator('[data-modal="seller-guide"]').locator('visible=true').count(): return
                pg.locator('[data-modal="seller-guide"]').locator('visible=true').first.click(); pg.locator('.ai-faq details').evaluate_all('els => els.forEach(e => e.open = true)'); grab('Seller Q&A'); esc()
            step('Seller Q&A', guide)
            def tour():
                if not pg.locator('[data-tour-start]').locator('visible=true').count(): return
                pg.locator('[data-tour-start]').locator('visible=true').first.click()
                for i in range(9):
                    pg.locator('#ai-tour h2').wait_for(timeout=6000); grab(f'Tour {i + 1}'); pg.click('[data-tour-next]')
                pg.wait_for_timeout(300)
            step('Tour', tour)

            for a in ids:
                def account_pages(a=a):
                    open_account(a); open_all(); grab(f'{a}: overview')
                    for tab in ('people', 'activity', 'qualification'):
                        pg.locator(f'#ai-stage [data-tab="{tab}"]').first.click(); grab(f'{a}: {tab}')
                    pg.locator('#ai-stage [data-tab="people"]').first.click(); pg.wait_for_timeout(200)
                    for i in range(min(3, pg.locator('#ai-stage [data-person]').count())):
                        pg.locator('#ai-stage [data-person]').nth(i).click(); grab(f'{a}: contact {i + 1}'); esc()
                    pg.locator('#ai-stage [data-tab="activity"]').first.click(); pg.locator('#ai-stage [data-modal="note"]').first.click(); grab(f'{a}: add note'); esc()
                    pg.locator('#ai-stage [data-tab="overview"]').first.click(); pg.wait_for_timeout(200)
                    pg.locator('#ai-stage [data-modal="research"]').first.click(); grab(f'{a}: sources'); esc()
                    if pg.locator('#ai-stage [data-modal="health"]').count():
                        pg.locator('#ai-stage [data-modal="health"]').first.click(); grab(f'{a}: customer signals'); esc()
                    for i in range(min(2, pg.locator('#ai-stage [data-cite]').count())):
                        pg.locator('#ai-stage [data-cite]').nth(i).click(); grab(f'{a}: record {i + 1}'); esc()
                step(f'{a}: account', account_pages)
                def campaign(a=a):
                    open_account(a); pg.locator('#ai-stage [data-build-plan]').first.click(); pg.locator('#ai-plan-action').wait_for(state='visible', timeout=25000)
                    pg.wait_for_timeout(400); open_all(); grab(f'{a}: campaign')
                    if pg.locator('[data-modal="choose-person"]').count():
                        pg.locator('[data-modal="choose-person"]').first.click(); grab(f'{a}: change contact'); esc()
                    pg.click('#ai-approve-plan'); grab(f'{a}: campaign approved')
                step(f'{a}: campaign', campaign)
            step('Tasks, after approvals', lambda: (nav('tasks'), grab('My tasks: after approvals')))
            step('Focus, after approvals', lambda: (nav('focus'), open_all(), grab('My focus: after approvals')))
            step('Weekly brief, after approvals', lambda: (nav('briefs'), pg.locator('#ai-stage [data-brief-kind="weekly"]').first.click(), pg.click('#ai-compose-brief'), pg.locator('#ai-save-brief').wait_for(timeout=8000), grab('Weekly brief: after approvals'), esc()))
            step('Daily brief, after approvals', lambda: (nav('briefs'), pg.locator('#ai-stage [data-brief-kind="daily"]').first.click(), pg.click('#ai-compose-brief'), pg.locator('#ai-save-brief').wait_for(timeout=8000), grab('Daily brief: after approvals'), esc()))
            ctx.close()
        b.close()

    seen, unique = set(), []
    for f in findings:
        key = (f['rule'], f['match'].lower(), f['context'])
        if key not in seen: seen.add(key); unique.append(f)
    words = sum(len(s['text'].split()) for s in screens)
    result = {'url': url, 'ranAt': datetime.now().isoformat(timespec='seconds'), 'screens': len(screens), 'words': words, 'rules': [r[0] for r in RULES] + ['Banned name or analyst voice'],
              'findings': unique, 'walkerErrors': walker_errors, 'pageErrors': sorted(set(page_errors)), 'sidewaysScroll': overflow,
              'passed': not unique and not walker_errors and not page_errors and not overflow}
    (out / 'language_audit.json').write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
    (out / 'screens.txt').write_text('\n'.join(f"===== {s['screen']} =====\n{s['text']}\n" for s in screens), encoding='utf-8')
    lines = [f'# Wording audit', '', f'- Build: {url}', f'- Run: {result["ranAt"]}', f'- Screens and dialogs read: {len(screens)} ({words} words), at 1366 and 390 wide',
             f'- Wording findings: {len(unique)}', f'- Screens the walker could not open: {len(walker_errors)}', f'- Page errors: {len(result["pageErrors"])}', f'- Screens that scroll sideways: {len(overflow)}', '',
             '## Rules', ''] + [f'- {r}' for r in result['rules']] + ['', '## Findings', '']
    lines += [f"- **{f['rule']}** on {f['screen']}: `{f['match']}` in \"{f['context']}\"" for f in unique] or ['None.']
    lines += ['', '## Walker errors', ''] + ([f"- {e['screen']}: {e['error']}" for e in walker_errors] or ['None.'])
    lines += ['', '## Sideways scroll', ''] + ([f"- {o['screen']}: {o['scrollWidth']} wide in a {o['viewport']} window" for o in overflow] or ['None.'])
    (out / 'LANGUAGE_AUDIT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in result.items() if k != 'rules'}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--url', default='http://127.0.0.1:8767/'); ap.add_argument('--out', default='docs/language_audit')
    args = ap.parse_args(); sys.exit(0 if run(args.url, Path(args.out))['passed'] else 1)
