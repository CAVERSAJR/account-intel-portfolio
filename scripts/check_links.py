"""Open every public source and contact-profile link the workspace shows and record whether it still answers.

For contact profiles it also checks that the person's surname is on the page that answered.
A site that refuses automated requests is reported as "refused", not as working.

Usage:
  python scripts/check_links.py --out docs/release_checks
"""
from __future__ import annotations
import argparse, json, re, ssl, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9'})
    try:
        with urllib.request.urlopen(req, timeout=25, context=ssl.create_default_context()) as res:
            return res.status, res.geturl(), res.read(600_000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e: return e.code, url, ''
    except Exception as e: return 0, url, type(e).__name__


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', default='docs/release_checks'); args = ap.parse_args()
    data = json.loads((ROOT / 'workspace' / 'data.public.json').read_text(encoding='utf-8'))
    links = {}
    for s in data['sources']:
        if s.get('url'): links.setdefault(s['url'], {'url': s['url'], 'account': s['accountId'], 'uses': [], 'names': []})['uses'].append(s['id'])
    for c in data['contacts']:
        if c.get('url'):
            entry = links.setdefault(c['url'], {'url': c['url'], 'account': c['accountId'], 'uses': [], 'names': []}); entry['uses'].append(c['id']); entry['names'].append(c['name'])
    rows = list(links.values())
    with ThreadPoolExecutor(max_workers=6) as pool: results = list(pool.map(lambda r: fetch(r['url']), rows))
    for row, (status, final, body) in zip(rows, results):
        row['status'] = status
        row['result'] = 'answers' if 200 <= status < 300 else 'redirects scripts' if 300 <= status < 400 else 'gone' if status in (404, 410) else 'refused automated request' if status in (401, 403, 405, 406, 429, 503, 999) else 'no answer'
        row['redirectedHome'] = bool(200 <= status < 400 and re.sub(r'^https?://[^/]+', '', final).strip('/') == '' and re.sub(r'^https?://[^/]+', '', row['url']).strip('/') != '')
        if row['names'] and row['result'] == 'answers':
            text = re.sub(r'\s+', ' ', body).lower()
            row['nameOnPage'] = all(re.sub(r'[^a-z]', '', n.split()[-1].lower()) in re.sub(r'[^a-z ]', '', text) for n in row['names'])
        if not (200 <= status < 400): row['error'] = body if status == 0 else ''
    # Second look in a real browser for anything a plain request could not confirm.
    retry = [r for r in rows if r['result'] != 'answers' or r.get('nameOnPage') is False]
    if retry:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(); page = browser.new_page()
            for r in retry:
                try:
                    page.goto(r['url'], timeout=30000, wait_until='domcontentloaded'); page.wait_for_timeout(1500); text = page.inner_text('body').lower()
                    found = all(n.split()[-1].lower() in text for n in r['names'])
                    if len(text) > 200 and found: r['result'] = 'answers'; r['nameOnPage'] = True if r['names'] else r.get('nameOnPage'); r['confirmedInBrowser'] = True
                except Exception as e: r['browserError'] = str(e).splitlines()[0][:160]
            browser.close()
    summary = {k: sum(r['result'] == k for r in rows) for k in ('answers', 'redirects scripts', 'refused automated request', 'gone', 'no answer')}
    profiles = [r for r in rows if r['names'] and r['result'] == 'answers']
    out = {'ranAt': datetime.now().isoformat(timespec='seconds'), 'links': len(rows), 'summary': summary,
           'confirmedInBrowser': sum(bool(r.get('confirmedInBrowser')) for r in rows), 'profilesAnswering': len(profiles), 'profilesWithNameOnPage': sum(r.get('nameOnPage', False) for r in profiles),
           'redirectedToHomePage': [r['url'] for r in rows if r['redirectedHome']],
           'problems': [r for r in rows if r['result'] != 'answers' or r['redirectedHome'] or r.get('nameOnPage') is False], 'rows': rows}
    dest = Path(args.out); dest.mkdir(parents=True, exist_ok=True)
    (dest / 'links.json').write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding='utf-8')
    by_account = {}
    for r in rows: by_account.setdefault(r['account'], []).append(r)
    lines = ['# Public link check', '', f'- Run: {out["ranAt"]}', f'- Links: {len(rows)}', f'- Result: {json.dumps(summary)}', f'- Contact profile pages that answered: {len(profiles)}; with the surname on the page: {out["profilesWithNameOnPage"]}', '', '| Account | Links | Answer | Refused | Gone | No answer |', '|---|---|---|---|---|---|']
    for a, rs in sorted(by_account.items()):
        lines.append(f"| {a} | {len(rs)} | {sum(r['result'] == 'answers' for r in rs)} | {sum(r['result'] == 'refused automated request' for r in rs)} | {sum(r['result'] == 'gone' for r in rs)} | {sum(r['result'] == 'no answer' for r in rs)} |")
    lines += ['', '## Links to look at', ''] + ([f"- {r['account']}: {r['url']} · {r['result']} ({r['status']})" + (' · redirected to the home page' if r['redirectedHome'] else '') + (' · surname not found on the page' if r.get('nameOnPage') is False else '') for r in out['problems']] or ['None.'])
    (dest / 'LINKS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: out[k] for k in ('links', 'summary', 'confirmedInBrowser', 'profilesAnswering', 'profilesWithNameOnPage', 'redirectedToHomePage')}, ensure_ascii=False))
    for r in out['problems'][:40]: print(r['account'], r['status'], r['result'], r['url'], '' if r.get('nameOnPage') is not False else 'NAME NOT ON PAGE', 'HOME' if r['redirectedHome'] else '')


if __name__ == '__main__':
    main()
