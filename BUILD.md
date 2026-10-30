# BUILD.md — EarnScore: build specification for Claude Code

Read this file fully, then read `PROJECT.md` (what and why) and `DATA_SOURCES.md` (data rules). Follow `PROMPTS.md` stage by stage.

## 0. Operating rules (non-negotiable)

1. **Ask, never assume.** If anything is ambiguous, missing, or has more than one reasonable reading, STOP and ask me with the AskUserQuestion tool (or plain text). Do not invent credentials, API keys, regulations, numbers, copy, or product decisions. "I assumed X" is a failure.
2. **Ask these before writing code (Stage 0):**
   - Deployment target (Render / Railway / Fly.io / Vercel+backend / other) and whether I already have an account.
   - LLM provider and key for the language layer (Gemini / Claude / none). It must work without one (template fallback).
   - Do I have Setu Account Aggregator sandbox credentials? If not, build the statement-upload path and an `AAProvider` interface only.
   - Product name styling, logo, colours, team name to show (or use the defaults in section 9).
   - Database: SQLite (default, simplest to deploy) or Postgres.
3. **No failures.** After every stage: run the tests, start the app, hit the real endpoints, and open the real pages. Do not move on while anything fails. Fix root causes; never delete or weaken a test to make it pass.
4. **No placeholders.** No `TODO`, `lorem ipsum`, dead buttons, empty pages, `console.log` leftovers, or mocked responses in production code. Every button does something real.
5. **The UI must read as a finished product.** Never write the words "demo", "sample", "mock", "test data", "simulated" or "dummy" in any user-facing text. Describe features by what they do. (Data honesty is handled in `DATA_SOURCES.md` and the README, not by labelling the UI. Do not hide data provenance from me or from the code.)
6. **Never fabricate data provenance.** Everything computed must come from the database. Everything in the database must come from (a) a user's upload, (b) the AA provider interface, or (c) the seeded generator in `DATA_SOURCES.md`. Never hardcode scores, bands, EMIs or chart values anywhere in frontend or backend.
7. **Git:** do NOT run `git commit`, `git push`, or add any `Co-Authored-By` line. I commit and push myself. See section 11.
8. **Time budget:** I have about 6 hours. Prefer the simple, robust option. Cut scope in the order listed in section 12, and tell me before cutting.
9. **Report briefly** at the end of each stage: what works, what you verified, what you need from me.

## 1. Product in one paragraph

EarnScore scores how reliably a gig worker earns, not how much. It fuses income from bank accounts and platform payout statements into one reconciled ledger, removes predictable seasonality, computes five income-neutral pillars, outputs a score (0–100), band (A–E), confidence and a safe weekly EMI, and gives a lender's credit officer an evidence-linked report. The officer decides. The worker owns the passport, sees reasons in Tamil/Hindi/English and gets safe steps to improve.

## 2. Stack (ask before deviating)

| Layer | Choice |
| --- | --- |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| DB | SQLite file by default (Postgres via `DATABASE_URL`) |
| Auth | Email + password, bcrypt, JWT in httpOnly cookie, role-based access |
| Data/ML | pandas, numpy, statsmodels (STL), scikit-learn, interpret (EBM), optbinning (optional), fairlearn |
| Parsing | pdfplumber (PDF), csv/openpyxl (CSV/XLSX) |
| Frontend | React 18 + Vite + TypeScript + Tailwind, react-router, TanStack Query, Recharts, react-i18next |
| Language layer | Provider interface with LLM implementation and deterministic template fallback |
| Deploy | One Docker image: FastAPI serves the built frontend. Single URL. |
| Tests | pytest (backend), vitest (frontend), Playwright (one end-to-end flow) |

Repo layout:

```
/backend  app/{api,core,models,schemas,services,scoring,ingest,sim,i18n}  tests/  alembic/
/frontend src/{pages,components,api,i18n,lib}
/Dockerfile  /docker-compose.yml  /README.md  /.env.example  /Makefile
```

## 3. Roles and pages

Three roles, each with its own area after login.

**Worker**
- Register / login; profile (name, city, work type, languages).
- *Consents*: per-source consent records (purpose, scope, expiry 90 days default, revoke anytime).
- *Sources*: connect bank via AA provider; upload bank statement (CSV/XLSX/PDF) or platform payout statement (CSV/PDF); delete a source (removes its data).
- *My Earnings Passport*: score, band, confidence, safe EMI, five pillars with reasons, trend over time, Data Sufficiency breakdown.
- *How to improve*: tested recourse steps (see 6.7).
- *Share*: create expiring share links to a named lender; view/revoke.
- *Disputes*: raise a dispute on a score or decision; track status.
- Language switch (English / தமிழ் / हिन्दी) and "read aloud" (Web Speech API) on explanations.

**Credit officer (lender)**
- *Applications queue*: filter by band, confidence, status; routing flag "manual review required".
- *Application detail*: the evidence-linked lender report. Every pillar and factor opens the exact transactions behind it (drill-down table). Reconciliation summary (matched, flagged, excluded). Seasonality chart (raw vs adjusted). Suggested loan shape (weekly EMI on payout day, seasonal skip-week). Approve / Modify / Decline with mandatory reason code and note.
- *Portfolio & early warnings*: monthly refresh results; alert when bad-week floor drops more than 20% vs previous snapshot; suggest skip-week or restructure.
- *Disputes inbox* (grievance officer view).

**Auditor / admin**
- *Model card* per model version (features, weights, training data description, metrics).
- *Fairness*: approval and error gaps by group (uses the optional, consented `group_attr` field only for audit), proxy checks.
- *Drift*: feature distribution drift between snapshots.
- *Override log*: every officer decision and override with reason.
- *Validation*: results of the simulator-based evaluation vs the bureau-style baseline (see 7).
- *User & lender management*.

Seed three role accounts through a documented CLI command (`make seed`), never with hardcoded passwords in code; read initial passwords from env vars.

## 4. Data model (minimum)

`users, worker_profiles, lenders, consents, sources, raw_files, transactions (raw), ledger_entries (reconciled: kind = earned | self_transfer | refund | loan | expense | other, matched_to, platform, week), weekly_series, snapshots (score runs), pillar_scores, reason_codes, applications, decisions (with reason_code, note, officer_id), overrides, share_links, disputes, audit_log, model_versions, cohort_seasonality, sim_runs`.

Every score run stores: input hash, model version, all pillar values, confidence, safe EMI, and the ledger entry IDs behind each reason code (evidence links).

## 5. Ingestion and reconciliation

1. **Parsers**: CSV/XLSX with a column-mapping step (auto-detect date, narration, debit, credit, balance; if not confident, ask the user to map columns in the UI). PDF via pdfplumber with table extraction; if extraction fails, show a clear error and offer CSV. Never silently drop rows; report counts parsed vs skipped.
2. **Classification** of each credit: earned / self_transfer / refund / loan / other, with deterministic rules first (own-account detection, keywords such as "refund", "loan disbursal", payer IDs for known platforms). An optional LLM may tag only ambiguous narrations; rules are the fallback and always run offline.
3. **Reconciliation rule** (exact): a platform payout and a bank credit match when `|amount_diff| / payout_amount <= 1%` AND the credit date is 0–3 days after payout date AND the payer ID or narration matches the platform. Matched pairs count once. Unmatched payouts and unexplained large credits are flagged (not counted as earned).
4. **Anti-gaming flags**: round-trips between the worker's own accounts; one-off credits larger than 3× the median weekly income within 14 days before an application; payouts with no platform match.
5. Output: weekly series of earned income, active-hours (if provided), per-week source mix.

## 6. Scoring engine (exact; implement as pure, unit-tested functions)

### 6.1 Seasonality and volatility
- Weekly earned income `Y`. Decompose with STL (period 52) when ≥ 2 years; with shorter history, subtract the **cohort seasonal index** (same city + work type, stored in `cohort_seasonality`, learned from all workers in the DB) then take the residual. Fall back to a simple 4-week moving median if the cohort has fewer than 20 workers (and mark confidence accordingly).
- `V_res = std(residual) / mean(Y)`.

### 6.2 Pillars (each 0–100; constants live in `scoring/config.py`, never inline)
- **Consistency (25%)**: active-week share (weeks with earned income > 0), longest gap (days), payout regularity (coefficient of variation of inter-payout gaps).
- **Stability (25%)**: `1 − V_res` mapped via piecewise-linear curve, downside deviation, median weeks to recover to the 20th-percentile level after a dip.
- **Capacity (25%)**: bad-week floor `F20` = 20th-percentile weekly earned income over the last 26 weeks; essentials `E_ess` = rent + utilities + fuel + existing EMIs per week (from ledger debits, user-confirmable); score = share of `F20` left after `E_ess`, clipped and mapped to 0–100; debt-service ratio.
- **Discipline (15%)**: bounced auto-debits, on-time bill payments, days of cash buffer (average balance / daily spend), recurring savings.
- **Resilience (10%)**: platform concentration (Herfindahl), tenure per platform, earnings per active hour trend. **Never reward higher total hours; flag > 60 active hours/week as a sustainability risk shown in watch-outs.**

`EarnScore = 0.25*C + 0.25*S + 0.25*Cap + 0.15*D + 0.10*R`, rounded.

**Bands:** A ≥ 80, B 65–79, C 50–64, D 35–49, E < 35. (Ask me before changing.)

### 6.3 Data Sufficiency (separate, never part of the score)
`DSI = 0.4*min(months/12,1) + 0.3*min(sources/3,1) + 0.3*reconcile_rate`. Confidence: High ≥ 0.7, Medium 0.4–0.7, Low < 0.4. If Low, show "Not enough data yet — add: <specific source>" to the worker and never show a band as a verdict.

### 6.4 Safe EMI
`EMI_safe = α × (F20 − E_ess)`, `α` default 0.5, set per lender (stored). Never negative; if `F20 ≤ E_ess` show 0 and a capacity warning.

### 6.5 Routing rules
Band D/E, or Low confidence, or any anti-gaming flag → status `manual_review_required`. No application is ever auto-declined. Officer must give a reason code for every Approve/Modify/Decline and for every disagreement with the suggested outcome.

### 6.6 Model
- v1: expert scorecard (the weights above).
- v2: Explainable Boosting Machine (`interpret`) trained on simulator outcomes (section 7) with monotonic constraints (consistency, stability, capacity, discipline, resilience all non-decreasing). Registered as a new `model_version`. The admin can switch the active version. If the EBM fails validation (worse than v1 on the baseline comparison), keep v1 active and say so in the model card.
- An LLM is allowed only to (a) tag ambiguous narrations, (b) rewrite reason codes into plain language. **It must never alter a number.** Post-check: every number in generated text must match the source value, else use the template text.

### 6.7 Reason codes and recourse
- Reason codes come from each pillar's contribution, with evidence links to ledger entries.
- Recourse: only actionable features may change (cash buffer days, on-time bills, bounce avoidance, consistency of active weeks). Locked features: hours worked, number of platforms, income level. Implement as a constrained search over actionable features, re-score each candidate with the real scoring function, and show only steps that actually raise the band ("Keep at least 7 days of expenses in your account for 8 weeks to move from B to A"). Use DiCE only if it installs cleanly and works; otherwise the constrained search is the implementation.

## 7. Validation simulator

- Simulate ≥ 5,000 workers over 52–104 weeks: 4 persona types (rider on 2 apps, home-service professional with lumpy income, freelancer with irregular transfers, vendor with daily UPI collections), cohort seasonality (monsoon, festivals, a yearly dip), shocks (deactivation, illness, vehicle breakdown), expenses, and a loan with an EMI.
- **A worker defaults only when simulated cash cannot cover the EMI for three consecutive payout cycles.** Never derive default from the scoring features.
- Compare vs a bureau-style baseline (approve if a synthetic "bureau score" exists above a threshold; thin-file workers have none). Report: approval rate at equal default rate, AUC, KS, calibration by band, share of creditworthy workers wrongly rejected by the baseline.
- Fairness audit with Fairlearn on the optional group attribute; recourse-feasibility rate for Band C–E.
- Store all results in `sim_runs`; the Admin "Validation" page renders them. The page must state the simulation parameters truthfully (in an "About these results" panel).

## 8. Seeded data

Follow `DATA_SOURCES.md` exactly. The generator is deterministic (fixed seed), writes through the same ingestion path as user uploads (no special side door), and creates worker accounts with realistic profiles that the three roles can log into. Do not hardcode any derived value.

## 9. Design

- Clean, calm, trustworthy fintech look. Light theme default, dark mode optional. Neutral palette with one accent. One sans-serif font. Generous spacing, clear hierarchy.
- Mobile-first for the worker area. Desktop-first for officer/auditor tables.
- Accessible: labels, focus states, contrast, keyboard navigation.
- Every empty/loading/error state is designed (not blank). Real form validation with helpful messages.
- Charts: Recharts, with units, tooltips, and the finding in the title.
- Name: EarnScore. Tagline: "Prove how reliably you earn." Ask me for logo/colours.
- Pages must render without horizontal scroll at 360 px width.

## 10. API and quality

- OpenAPI docs at `/api/docs` (admin-only in production).
- Rate limiting on auth; CORS locked to the deployed origin; secure cookies; CSRF protection for cookie auth; password rules; input validation everywhere; file upload limits (10 MB) and type checks; uploaded files stored outside the web root; raw file deletion on source removal.
- DPDP-minded: consent required before any ingestion; purpose and expiry stored; revoke removes access and schedules deletion; no SMS/contacts/call logs/location collected anywhere.
- Audit log for every read of a worker's report by a lender and every decision.
- Health check `/healthz`; structured logs; no secrets in repo; `.env.example` complete.
- Tests must cover: parsers, reconciliation rule edge cases (1% tolerance, 0–3 day window, duplicates), seasonality, each pillar, bands, DSI, safe EMI, routing, recourse validity, auth/role access, consent revocation, share-link expiry, and one Playwright end-to-end flow: worker uploads data → score → shares → officer reviews → decides → worker sees decision.

## 11. Git and attribution (so Claude is not a contributor)

- Create `.claude/settings.json` in the repo with:
  ```json
  { "attribution": { "commit": "", "pr": "" }, "includeCoAuthoredBy": false }
  ```
- Add `.claude/` and `CLAUDE.md` to `.gitignore` if I ask to keep the repo clean.
- Do not commit or push. I will run `git init`, `git add`, and `git commit` with my own name and email, then push.
- Before I push, run `git log --format=full` (after my first commit) and confirm there is no `Co-Authored-By` line. If one appears, tell me and I will amend it.

## 12. If time runs short, cut in this order (ask first)

1. DiCE (keep constrained search).  2. EBM v2 (keep scorecard v1, state it honestly in the model card).  3. PDF parsing (keep CSV/XLSX).  4. Voice read-aloud.  5. Dark mode.  6. Drift page.  Never cut: login and roles, consent, reconciliation, five pillars, evidence drill-down, safe EMI, human decision with reason code, worker explanations, audit log, deployment.

## 13. Definition of done

- [ ] `docker compose up` starts everything; `make test` passes; Playwright flow passes.
- [ ] All three roles can log in and use every page with no dead ends.
- [ ] A user can upload a real bank statement CSV and get a complete report.
- [ ] Every number on screen traces to the database; no hardcoded results; no placeholders; no "demo/sample/mock" wording in the UI.
- [ ] Hindi/Tamil/English switch works on all worker pages.
- [ ] README includes setup, env vars, architecture, data provenance, and limitations, written honestly.
- [ ] Deployed and reachable at a single HTTPS URL; I have the URL and logins.
- [ ] I have a one-page "what is real vs generated" summary from `DATA_SOURCES.md`.
