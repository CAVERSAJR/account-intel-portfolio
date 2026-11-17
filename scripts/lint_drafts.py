import json, sys, re, statistics
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from language_audit import lint
rows = json.load(open(sys.argv[1], encoding='utf-8')); rows = rows if isinstance(rows, list) else rows.get('results', rows)
hits, words, secs, starts = [], [], [], {}
for r in rows:
    if not r.get('ok'): print('FAILED', r['id'], r.get('error')); continue
    text = '\n'.join([*(r['fields'] or {}).values(), *[q if isinstance(q, str) else json.dumps(q) for q in r['questions']], r['email']['subject'], r['email']['body']])
    hits += lint(f"{r['id']} r{r['round']}", text); words.append(r['email']['words']); secs.append(r['seconds'])
    first = re.split(r'\n+', r['email']['body'].strip()); line = first[1] if len(first) > 1 and re.match(r'^(hi|hello|dear)\b', first[0], re.I) else first[0]
    starts[' '.join(line.split()[:3])] = starts.get(' '.join(line.split()[:3]), 0) + 1
    if len(sys.argv) > 2 and r['round'] == int(sys.argv[2]): print('-----', r['id'], '|', r['email']['subject'], '|', r['email']['words'], 'words'); print(r['email']['body']); print()
print('drafts', len(rows), 'lint hits', len(hits)); [print(h) for h in hits[:30]]
print('email words: median', statistics.median(words), 'max', max(words), 'over 75:', sum(w > 75 for w in words), 'over 110:', sum(w > 110 for w in words))
print('seconds: median', statistics.median(secs), 'max', max(secs)); print('email opening words:', sorted(starts.items(), key=lambda x: -x[1]))
