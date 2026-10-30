# EarnScore

**Prove how reliably you earn.**

EarnScore scores how reliably a gig worker earns, not how much. It fuses income from bank statements and platform payout statements into one reconciled ledger (each rupee counted once), removes predictable seasonality, computes five income-neutral pillars, and outputs a score (0–100), a band (A–E), a confidence level and a safe weekly EMI. A lender's credit officer gets an evidence-linked report and makes the decision; the worker owns the passport, sees reasons in English, Tamil or Hindi, and gets tested steps to improve.

Built for the RAISE hackathon, Problem Statement 2.

---

## Contents

1. [Quick start](#quick-start)
2. [Environment variables](#environment-variables)
3. [Architecture](#architecture)
4. [How scoring works](#how-scoring-works)
5. [Data provenance: what is real and what is generated](#data-provenance-what-is-real-and-what-is-generated)
6. [Validation results](#validation-results)
7. [Limitations](#limitations)
8. [Tests](#tests)
9. [Deployment](#deployment)

---

## Quick start

### Docker (one image, one URL)

```bash
cp .env.example .env        # then set SECRET_KEY and the SEED_* passwords
docker compose up --build   # builds the frontend, the API, the generated dataset and the validation run
open http://localhost:8000
```

The image build runs the generator and the 5,000-worker simulator (deterministic; takes several minutes). On start the container applies migrations, creates the three role accounts from the `SEED_*` variables, and serves the API and the built frontend from the same origin.

### Local development

```bash
make install                 # Windows: mingw32-make install (or run the commands in the Makefile)
make data                    # migrate + generate + simulate + seed  (reads .env)
make dev-api                 # FastAPI on :8000
make dev-web                 # Vite on :5173 (proxies /api to :8000)
make test                    # pytest + vitest + Playwright (needs the API running on :8000 with a built frontend)
```

### Logins

`make seed` creates (from env vars, never from code):

| Role | Email | Password |
| --- | --- | --- |
| Auditor / admin | `SEED_ADMIN_EMAIL` | `SEED_ADMIN_PASSWORD` |
| Credit officer (Nilavu Community Credit) | `SEED_OFFICER_EMAIL` | `SEED_OFFICER_PASSWORD` |
| Worker with no data yet (for the upload flow) | `SEED_WORKER_EMAIL` | `SEED_WORKER_PASSWORD` |
| 24 generated workers, e.g. `karthik.subramanian@example.com` | see `backend/app/sim/generate.py` (`NAMED`) | `SEED_WORKER_PASSWORD` |

## Environment variables

All variables are listed with comments in [`.env.example`](.env.example).

| Variable | Purpose |
| --- | --- |
| `ENV` | `production` turns on secure cookies and admin-only API docs at `/api/docs` |
| `SECRET_KEY` | signs session tokens (required) |
| `ALLOWED_ORIGIN` | the single origin allowed by CORS (the deployed URL) |
| `DATABASE_URL` | SQLite by default (`backend/data/earnscore.db`); a Postgres URL also works |
| `DATA_DIR`, `UPLOAD_DIR` | database, generated statements, model artifacts; uploaded files (outside the web root) |
| `SESSION_HOURS`, `MAX_UPLOAD_MB`, `CONSENT_DEFAULT_DAYS`, `CONSENT_PURGE_DAYS` | session length, 10 MB upload limit, 90-day consent default, 7-day deletion grace after revocation |
| `LLM_PROVIDER`, `GEMINI_API_KEY`, `GEMINI_MODEL` | optional language layer; without a key, template text is used |
| `SEED_*` | emails and passwords for the role accounts created by `make seed` |

## Architecture

```
 Browser (React 18 + Vite + TS + Tailwind, react-router, TanStack Query, Recharts, react-i18next)
   │  same origin, JWT in httpOnly cookie, CSRF double-submit header
   ▼
 FastAPI (backend/app/main.py) ─── /healthz, /api/docs (admin-only in production)
   ├─ api/        auth · worker · officer · admin routers, role checks, audit on every lender read and decision
   ├─ ingest/     parsers (CSV/XLSX/PDF + column mapping) → classify (rules) → reconcile (1% / 0–3 days / payer)
   │              → ledger_entries (kind, counted, matched_to, flags) → weekly_series;  aa.py = AAProvider interface
   ├─ scoring/    config.py (every constant) · engine.py (pure functions: seasonality, pillars, score, DSI,
   │              safe EMI, routing, reason codes) · recourse.py (constrained search) · loan.py (loan shape)
   ├─ services/   snapshots (inputs from the ledger, input hash, model version) · reports (passport, lender
   │              report, evidence) · applications (share links, decisions, overrides, monthly refresh)
   │              · consent (grant / revoke / purge) · cohort (seasonal index) · model_registry · language
   ├─ sim/        life.py (worker cash-flow model) · generate.py (statements → upload pipeline)
   │              · simulate.py (validation, bureau baseline, fairness, EBM v2)
   └─ i18n/       reason, watch-out and recourse templates in en / ta / hi
   ▼
 SQLite (SQLAlchemy 2 + Alembic) · uploaded files under UPLOAD_DIR
```

One Docker image: the frontend is built in a Node stage and served by FastAPI.

## How scoring works

All formulas are in `backend/app/scoring/engine.py`; every constant is in `backend/app/scoring/config.py`.

- **Weekly earned income** comes only from ledger entries marked `counted` (earned credits; a matched platform payout and its bank credit count once; self-transfers, refunds, loans, unmatched payouts and unexplained large credits are not counted).
- **Seasonality**: STL (period 52, robust, seasonal shape held constant across years so only what repeats counts as seasonal) with ≥ 2 years of history; otherwise the cohort seasonal index (same city + work type, the per-week mean of every cohort worker's normalised income, bounded to 0.5–2.0) when the cohort has ≥ 20 workers; otherwise a 4-week moving median, and confidence is capped at Medium. `V_res = std(residual) / mean(Y)`.
- **Pillars (0–100)**: Consistency 25%, Stability 25%, Capacity 25%, Discipline 15%, Resilience 10%. `EarnScore = 0.25C + 0.25S + 0.25Cap + 0.15D + 0.10R`. Income level and hours worked are never inputs; more than 60 active hours a week is shown as a watch-out.
- **Bands**: A ≥ 80, B 65–79, C 50–64, D 35–49, E < 35.
- **Data Sufficiency** (separate from the score): `DSI = 0.4·min(months/12,1) + 0.3·min(sources/3,1) + 0.3·reconcile_rate`; High ≥ 0.7, Medium 0.4–0.7, Low < 0.4. With Low confidence the worker sees "Not enough data yet — add: …" and no band verdict.
- **Safe EMI** = α × (F20 − weekly essentials), α = 0.5 by default and set per lender; never negative.
- **Routing**: Band D/E, Low confidence or any anti-gaming flag → manual review. Nothing is ever declined automatically; every officer decision needs a reason code.
- **Recourse**: only cash buffer, on-time bills, bounce avoidance and active-week consistency may change; every step is re-scored with the real scoring function and shown only if it raises the band.
- **Language layer**: an LLM (Gemini, optional) may only rewrite reason text and tag ambiguous narrations. Every number in generated text must equal the template's numbers or the template text is used.

## Data provenance: what is real and what is generated

| Item | Status | Source |
| --- | --- | --- |
| Scoring logic, reconciliation, seasonality, pillars, bands, safe EMI | **Real computation** | Code in `backend/app/scoring` and `backend/app/ingest`, run on whatever data is in the database |
| Login, roles, consent, audit log, share links, disputes, decisions | **Real functionality** | Database writes by actual users |
| Bank statements and platform payout statements uploaded by a user | **Real data path** | The user's own files (CSV/XLSX/PDF). Any genuine statement works. |
| Account Aggregator connection | **Not connected.** No Setu credentials were provided. The `AAProvider` interface exists (`backend/app/ingest/aa.py`) and the upload path is used. Real AA needs a regulated lender as the data recipient. | — |
| Worker accounts and transaction histories pre-loaded for the evaluation (24 named workers + 588 cohort members) | **Generated** | Deterministic generator (`backend/app/sim/generate.py`, seed 20261030). They are not real people or real bank records. Statements are written as files in five formats and ingested through the normal upload pipeline. |
| Past applications and decisions of generated workers, and the officer "R. Lakshmi" who made them | **Generated** | Same generator, applying a fixed policy to computed reports |
| Cohort seasonality indices | **Derived** | Computed from the weekly series in the database (generated plus uploaded) |
| Validation results (approval uplift, AUC, KS, fairness gaps, recourse feasibility, EBM comparison) | **Simulated** | `backend/app/sim/simulate.py`. They show how the method behaves under stated assumptions, not real-world accuracy. |
| Market numbers (12M workers, 23.5M, 40% under ₹15,000) | **Cited** | Economic Survey 2025-26, NITI Aayog; used only in the pitch, not computed |
| Platform names (Swiggy, Zomato, Uber, Rapido, Urban Company) in generated statements | **Labels only** | No data was obtained from these companies and no partnership exists |
| Bank names in generated statements (Pallava, Vijayanagar, Konark, Satpura Bank) and lenders (Nilavu Community Credit, Prakriti Gig Finance) | **Fictional** | Invented names. Account numbers start `9999 0000`, phone numbers `+91 10000`, emails use the reserved `example.com` domain. |

No SMS, contacts, call logs or location are collected anywhere. Uploaded data belongs to the uploader, can be deleted by them, and is never used for training without the explicit training consent flag on the profile.

## Validation results

From the stored simulation run (seed 72026, 5,000 simulated workers, 26–78 weeks of history then 26 weeks of repayment). The Admin → Validation page renders the live values and an "About these results" panel with every parameter. **These are simulated results under stated assumptions, not evidence of real-world accuracy.**

| Metric | Value |
| --- | --- |
| AUC / KS, EarnScore vs simulated default | 0.877 / 0.644 |
| AUC of the synthetic bureau score (file holders only) | 0.693 |
| Workers with a bureau file | 39.9% |
| Bureau-style baseline: approval rate / default rate among approved | 27.9% / 13.2% |
| EarnScore at the same default rate: approval rate / default rate | 90.9% / 13.2% (3.26× the baseline's approvals) |
| Creditworthy workers rejected: baseline vs EarnScore at equal default | 70.4% vs 3.4% |
| EarnScore "approve Bands A–C": approval / default | 72.8% / 5.3% |
| Default rate by band A / B / C / D / E | 1.6% / 5.4% / 12.8% / 44.6% / 69.3% |
| Default rate by confidence High / Medium / Low | 8.1% / 30.4% / 39.8% |
| Recourse feasibility (Band C–E, 600 evaluated) | 26.3% have a tested step that raises their band |
| EBM v2 vs v1 on the 30% hold-out (AUC) | 0.902 vs 0.889 (same approvals at equal default, 91.3%); v2 passed validation but v1 stays active until an admin switches |

What these numbers do and do not show:

- Defaults come only from simulated cash shortfalls (three consecutive uncovered EMI cycles), never from the scoring features. But the same simulator produces both the history that is scored and the repayment period, so the AUC reflects how well the pillars capture the simulator's own mechanics.
- The bureau baseline is synthetic: a file exists for 70% of workers with an existing loan and 15% otherwise; its score is driven by bounced EMIs on that loan plus noise. Much of the uplift comes from the 60% of thin-file workers the baseline cannot approve at all.
- Simulated vendors never defaulted (0.0%) and freelancers defaulted 57.7% of the time. Both say more about the generator's persona assumptions than about real vendors or freelancers.
- Fairness (Admin → Fairness) uses a generated group attribute; it is an audit of the method under these assumptions only.

## Limitations

- Validation is simulated until a real pilot; there is no claim of real-world accuracy.
- Pre-loaded worker histories are generated, not real people.
- Real Account Aggregator data needs a regulated lender partner; statement upload is the working path.
- Platform APIs depend on partnerships; platform payouts come from statements the worker uploads.
- The weekly formulas in the specification (active-week share, 20th-percentile weekly floor) penalise freelancers who are paid in lumps a few times a month: many of their weeks show zero income, so F20 is often ₹0 and they land in Band D/E. This was left as specified, not tuned.
- Any single platform payout without a bank credit within 1% and 0–3 days raises an anti-gaming flag and routes the application to manual review, which is frequent for long histories.
- PDF parsing supports text-based statements with a ruled transaction table; scanned images are rejected with a clear message.
- Tamil and Hindi text was written by the developer and needs review by native speakers.
- On Render's free plan the disk is not persistent: each restart returns to the generated dataset baked into the image, and changes made by users are lost. A paid persistent disk mounted at `/app/backend/data` removes this.
- Market numbers use the team's assumptions for price and usage.

## Tests

- `backend/tests` (pytest): parsers (CSV formats, XLSX, PDF, scanned PDF, malformed rows), reconciliation edge cases (1% tolerance, 0–3 day window, payer match, duplicates), classification and round trips, seasonality (STL, cohort, fallback), each pillar, bands, DSI, safe EMI, routing, reason-code evidence, recourse validity, loan shape, auth and role access, CSRF, rate limiting, consent revocation, duplicate uploads, column mapping, source deletion, upload limits, share-link expiry, audit writes, the full API flow, and the language post-check (an LLM cannot change any number or the score).
- `frontend/src/**/*.test.ts` (vitest): formatting, translation key coverage and placeholder parity, forbidden wording.
- `frontend/e2e/flow.spec.ts` (Playwright): worker registers, consents, uploads a bank and two payout statements, sees the passport and evidence, switches language, shares with a lender; officer opens the report and drill-downs, decides with a mandatory reason code; worker sees the decision.

## Deployment

`render.yaml` deploys the Docker image to Render as one web service with `/healthz` as the health check. Set `ALLOWED_ORIGIN` to the service URL and the `SEED_*` variables in the Render dashboard; `SECRET_KEY` is generated. `GEMINI_API_KEY` is optional.
