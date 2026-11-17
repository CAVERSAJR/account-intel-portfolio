# Account Intel

A workspace that tells a seller where to start. It ranks a book of accounts from public sources, explains each rank, drafts the campaign with a live model call, checks the draft in code, and keeps the seller in charge of what gets approved.

**Live demo:** https://account-intel-live.vercel.app

Built for the moment a seller inherits a book of accounts or comes back from leave and needs to get current fast: which five accounts this week, why now, who to talk to, and what to say first.

## Where it came from

I used to build account intelligence reports for sellers by hand: spreadsheets with a brief of each seller's top five accounts for the week, refreshed about once a month in my AI office hours. I turned that into a first version on Lovable for an external hack day, then rebuilt and extended it with Claude Code and DeepSeek into this.

## What it does

- **My focus.** Eleven private-markets accounts ranked before the seller opens the page, from 128 public sources and 104 researched contacts. Each account shows its score, the reason to look, the entry-point person and the next move.
- **Why this account.** A 0–10 score from four drivers: fund timing (4), fit (3), buyer access (2) and signal strength (1). Each driver shows its points and the line that earned them.
- **Prepare campaign.** One live model call reads only that account's active sources and drafts goals, pain to confirm, who to talk to, the angle, the next step and an email. Code checks it before the seller sees it.
- **The seller decides.** Edit the next step, approve the plan. Approval saves the plan; nothing is ever emailed.
- **Change an input.** Turn a source off and the score, priority and plan move with it. An approved plan built on that source is marked out of date.
- **Catch me up.** A handover brief for a new book, or a return brief after 2, 3 or 4 weeks away, plus a plan for the week across five accounts with named people and titles.

Account facts come from public sources and link to them. Buyer activity in the demo is made up and labelled "Simulated activity". The public build removes contact emails and profile links; names and titles come from each firm's own pages.

## How it's built

| Part | What it is |
|---|---|
| `app/` | The deployed site: one HTML page, the bundled engine, and two Vercel serverless functions (`api/draft.js`, `api/status.js`) |
| `workspace/` | TypeScript scoring engine (`domain.ts`, `engine-core.ts`), the public dataset, and unit tests |
| `server/` | A small Python server for running locally: serves `app/`, proxies the model call, same checks as the hosted function |
| `scripts/` | Browser simulations and release checks (Playwright), wording audit, live-draft runner |

**Where the AI is, and where it isn't.** The model drafts the plan and the email. Ranking, the score, the draft checks and the approval rules are plain code, so a seller can see why an account is where it is, and the same inputs always give the same ranking.

**The checks.** Every claim must cite a real, active source for that account. Hypotheses stay labelled as hypotheses; anything the sources can't support stays unknown. The email must go to the chosen contact, stay short and avoid a list of filler phrases. If a draft fails, the screen says so and the model redrafts once; if the model is down, the seller's work is kept.

**Model.** DeepSeek through a direct API call (no framework: it's one structured call). The provider sits behind one function; the same app also runs against a local model through Ollama with the same checks.

## Run it locally

Requires Python 3.10+ and Node 20+.

```bash
npm install
npm test                       # engine tests (vitest)
python -m pytest server -q     # server tests
node scripts/check_hosted_rules.mjs
```

Serve the app with live drafts (set your own key; without one the app still runs and uses its prepared drafts):

```bash
DEEPSEEK_API_KEY=... python server/server.py --port 8767 --static app
```

Then open http://127.0.0.1:8767. Browser simulations need Playwright (`pip install playwright && python -m playwright install chromium`):

```bash
python scripts/simulate_sellers.py --url http://127.0.0.1:8767/ --out docs/simulations
```

Rebuild the browser engine after changing `workspace/`: `npm run build:engine`.

## Tests

- 50 engine tests, 43 server tests, 18 hosted-function rule checks.
- 15 scripted seller scenarios (118 checks) in a real browser: Monday seller, new rep, back from leave, stale plan, model outage, rapid clicks, phone width, blocked storage.
- A wording audit across 341 screens and dialogs, and release checks for headers, speed, accessibility, keyboard use and Safari's engine.
