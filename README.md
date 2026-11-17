# Account Intel

A seller workspace for a new book of accounts or a return from leave: which accounts to work this week, why, who to talk to, and what to do next.

**Live demo:** https://account-intel-live.vercel.app

I built Account Intel using AI-assisted development, based on account briefs I previously prepared for sellers.

## Product focus

This version focuses on one product: LP-obligation tracking for private-markets firms. Fund and firm signals give a seller a reason to investigate an account. The output is a hypothesis to confirm and questions for discovery, not confirmed pain or qualification. Whether the firm has the problem, what it costs them, and whether the product fits is for the seller to establish with the buyer.

## Inputs

- **Prepared public research:** 11 accounts (9 net new, 2 customers), 128 linked public sources and 104 researched contacts, with names and titles from each firm's own website. Every source links to the page it came from.
- **Simulated activity:** buyer signals and customer health are made up for the demo and labelled "Simulated activity" or "Simulated data" wherever they appear. Every account starts in initial outreach: no prior call, known pain or booked meeting.
- **Not connected:** this build has no live connection to a CRM, a fund database, a contact-enrichment tool or LinkedIn. The public build shows firm team-page links and leaves out contact emails and LinkedIn profiles.

## What it does

- **My focus.** The accounts are ranked before the seller opens the page. Each shows its score, the reason to look, the entry-point person and the next move, plus an estimate of time back this week.
- **Why this account.** A 0–10 score from four visible drivers: Fund lifecycle (4), ICP fit (3), Buyer access (2) and Signal strength (1). It tells a seller where to look; it does not predict who will buy. The weights are design choices, not a fitted model.
- **Catch me up.** A brief for a new account list, or a return brief after 2, 3 or 4 weeks away. Sections are Your priority accounts, Customer priorities, Gaps to close and Plan for the week, with a firm-profile link beside each person so the seller can check the recommendation.
- **Prepare campaign.** One live model call reads only that account's active sources and drafts goals, pain to confirm, who to talk to, the angle, discovery questions, the next step and an email.
- **Review and approve.** The seller edits the next step and approves the plan. Approval adds that exact step to My tasks. It does not change the buyer's stage, confirm the buyer's problem, change qualification or write to a CRM, and nothing is ever emailed.
- **Discovery meeting.** When a buyer replies, the seller records the reply; only then does the stage change. A meeting counts as booked only after the seller marks it confirmed. A confirmed meeting gets an internal pre-call plan: objective, time, primary prospect and attendees (confirmed or not), the seller as meeting owner, why now with sources, an agenda that can be shared, and separately the internal hypotheses, questions and unknowns. After the call the seller records what the buyer said, what was confirmed, what is still unknown, the agreed step with owner and date, and any dependencies or blockers. Nothing there is written by AI, and none of it changes qualification automatically.
- **Tasks and calendar.** Approved tasks start under Not scheduled. The seller sets a date, and only then can a task open a prefilled all-day Google Calendar draft. A recorded meeting can open a timed draft with the shareable agenda. The seller sets the reminder and saves it in Google Calendar; opening a draft does not book anything. This is a one-way handoff, not a sync.
- **Daily and weekly briefs.** Built from tasks and plans; a saved brief is flagged when tasks, replies or meetings change. Saving a brief never approves anything or creates tasks.
- **Print / Save PDF.** A weekly report built from the current state: the priority accounts with why now and its source, pain and questions from the reviewed plan (or marked as a prepared suggestion), people with profile links, actions marked Approved or Suggested, task dates, and any recorded reply, meeting and agreed step. The pre-call plan prints on its own, with the seller's notes.
- **Change an input.** Turn a source off and the score and priority move with it. An approved plan built on that source has its approval withdrawn and is flagged for another review.

## Where the AI is, and where it isn't

- **AI drafts** the campaign plan and the email for one account at a time.
- **Code controls** the ranking, the score, the request and response checks, account rules (for example, no expansion talk while a customer has an open service issue), the approval rules, tasks, briefs and the report. Catch me up and the weekly brief are built by code, not by extra model calls.
- **The seller reviews** whether the sources support what the draft says, edits it and approves it.

The checks confirm that each citation points to a real, active source supplied for that account, that hypotheses are labelled as hypotheses, that unsupported fields stay unknown, and that an email never tells the buyer we saw their page views, visits or email opens. A valid citation shows where a claim points; it does not prove the inference is right, which is why the seller reviews it. If a draft fails the checks, the screen says so and the model redrafts once. If a regeneration fails, the previous plan, its edits, approval and tasks are kept and the failed attempt is shown separately; a failed first draft shows a prepared draft labelled as not an AI result.

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
- 71 checks for the two-stage workflow: no invented contact at the start, reply and meeting only when recorded, the pre-call plan, notes that persist, briefs that notice changes, and tasks, calendar drafts and PDFs that agree.
- 23 checks for failed regeneration: an approved, edited plan and its tasks survive a provider failure, an outdated plan stays flagged, a failed first draft is labelled as prepared, and a successful regenerate still asks for review.
- A wording audit across 341 screens and dialogs, and release checks for headers, speed, accessibility, keyboard use and Safari's engine.

## Current limitations

- One product lens (LP-obligation tracking); no comparison across products.
- Research is prepared ahead of time; there are no live data connections, and contact titles can go out of date.
- Workspace state lives in the browser, not a shared database, and the app's date is fixed at November 16, 2026.
- The calendar handoff opens a draft; saving it, reminders and any later changes happen in Google Calendar.
- Replies and meetings are entered by the seller; there is no inbox or calendar connection.
- PDF export uses the browser's print dialog.
- Approval does not enforce a fresh draft after the evidence changes; it withdraws the approval and flags the plan instead.
- Tested in Chromium and WebKit; not in Firefox or on a real phone.
