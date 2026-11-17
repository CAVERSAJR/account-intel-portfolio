# Account Intel

A seller workspace for a new book of accounts or a return from leave: which accounts to work this week, why, who to talk to, and what to do next.

**Live demo:** https://account-intel-live.vercel.app

I built Account Intel using AI-assisted development, based on account briefs I previously prepared for sellers.

## Product focus

This version focuses on one product: LP-obligation tracking for private-markets firms. Fund and firm signals give a seller a reason to investigate an account. The output is a hypothesis to confirm and questions for discovery, not confirmed pain or qualification. Whether the firm has the problem, what it costs them, and whether the product fits is for the seller to establish with the buyer.

## Inputs

- **Prepared public research:** 11 accounts (9 net new, 2 customers), 128 linked public sources and 104 researched contacts, with names and titles from each firm's own website. Every source links to the page it came from.
- **Simulated activity:** stages, calls, meetings, email opens and customer health are made up for the demo and labelled "Simulated activity" or "Simulated data" wherever they appear.
- **Not connected:** this build has no live connection to a CRM, a fund database, a contact-enrichment tool or LinkedIn. The public build shows firm team-page links and leaves out contact emails and LinkedIn profiles.

## What it does

- **My focus.** The accounts are ranked before the seller opens the page. Each shows its score, the reason to look, the entry-point person and the next move, plus an estimate of time back this week.
- **Why this account.** A 0–10 score from four visible drivers: Fund lifecycle (4), ICP fit (3), Buyer access (2) and Signal strength (1). It tells a seller where to look; it does not predict who will buy. The weights are design choices, not a fitted model.
- **Catch me up.** A handover brief for a new book, or a return brief after 2, 3 or 4 weeks away. Sections are Start here, Defend the house, Gaps to close and Plan for the week, with a firm-profile link beside each person so the seller can check the recommendation.
- **Prepare campaign.** One live model call reads only that account's active sources and drafts goals, pain to confirm, who to talk to, the angle, discovery questions, the next step and an email.
- **Review and approve.** The seller edits the next step and approves the plan. Approval adds the plan's next steps to My tasks. It does not confirm the buyer's problem, change qualification or write to a CRM, and nothing is ever emailed.
- **Tasks and calendar.** Tasks start undated. The seller picks a date, and only then can a task open a prefilled, all-day Google Calendar draft. The seller sets the time and reminder and saves it in Google Calendar. This is a one-way handoff, not a sync: a saved event does not change if the plan changes later.
- **Print / Save PDF.** A weekly report built from the current state: the five accounts with why now and its source, pain and questions from the reviewed plan (or marked as a prepared suggestion), people with profile links, actions marked Approved or Suggested, and task dates.
- **Change an input.** Turn a source off and the score and priority move with it. An approved plan built on that source has its approval withdrawn and is flagged for another review.

## Where the AI is, and where it isn't

- **AI drafts** the campaign plan and the email for one account at a time.
- **Code controls** the ranking, the score, the request and response checks, account rules (for example, no expansion talk while a customer has an open service issue), the approval rules, tasks, briefs and the report. Catch me up and the weekly brief are built by code, not by extra model calls.
- **The seller reviews** whether the sources support what the draft says, edits it and approves it.

The checks confirm that each citation points to a real, active source supplied for that account, that hypotheses are labelled as hypotheses, and that unsupported fields stay unknown. A valid citation shows where a claim points; it does not prove the inference is right, which is why the seller reviews it. If a draft fails the checks, the screen says so and the model redrafts once; if the model is down, the seller's work is kept.

## How it's built

| Part | What it is |
|---|---|
| `app/` | The deployed site: one HTML page, the bundled engine, and two Vercel serverless functions in JavaScript (`api/draft.js`, `api/status.js`) that call DeepSeek directly |
| `workspace/` | TypeScript scoring engine (`domain.ts`, `engine-core.ts`), the public dataset, and unit tests |
| `server/` | A small Python server for running locally: serves `app/`, proxies the model call, applies the same checks as the hosted function |
| `scripts/` | Playwright browser simulations and release checks, wording audit, live-draft runner |

Measured on each draft: time to draft, sources read and claims sourced. The weekly time-back figure on My focus is an estimate, not a measurement.

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

Then open http://127.0.0.1:8767. Browser checks need Playwright (`pip install playwright && python -m playwright install chromium`):

```bash
python scripts/simulate_sellers.py --url http://127.0.0.1:8767/ --out docs/simulations
python scripts/seller_feedback_checks.py http://127.0.0.1:8767/ docs/seller_feedback
```

Rebuild the browser engine after changing `workspace/`: `npm run build:engine`.

## Tests

- 50 engine tests, 43 server tests, 18 hosted-function rule checks.
- 15 scripted seller scenarios (118 checks) in a real browser: Monday seller, new rep, back from leave, stale plan, model outage, rapid clicks, phone width, blocked storage.
- 57 checks for profile links, section layout at 360, 390 and 430 px, task dates, the calendar handoff and the PDF report.
- A wording audit across 341 screens and dialogs, and release checks for headers, speed, accessibility, keyboard use and Safari's engine.

## Current limitations

- One product lens (LP-obligation tracking); no comparison across products.
- Research is prepared ahead of time; there are no live data connections, and contact titles can go out of date.
- Workspace state lives in the browser, not a shared database, and the app's date is fixed at November 16, 2026.
- The calendar handoff opens a draft; saving it, reminders and any later changes happen in Google Calendar.
- PDF export uses the browser's print dialog.
- Approval does not enforce a fresh draft after the evidence changes; it withdraws the approval and flags the plan instead.
- Tested in Chromium and WebKit; not in Firefox or on a real phone.
