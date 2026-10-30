# EarnScore — handover

## 1. Where it runs

| Target | Status |
| --- | --- |
| Docker (`docker compose up --build`) | **Verified.** Serves the app and API at http://localhost:8000 from one image; `/healthz` returns `{"status":"ok"}`; the full Playwright suite (9 tests) passes against the container. |
| Render (single HTTPS URL) | **Ready, not yet deployed.** `render.yaml` is in the repo. Render builds from GitHub, so it needs your push (section 6) and a click on *New → Blueprint* in the Render dashboard. Set `ALLOWED_ORIGIN` to the service URL and the six `SEED_*` variables. The free plan has no persistent disk: each restart returns to the generated dataset in the image. |
| ngrok (backup HTTPS URL to the local container) | **Needs your ngrok authtoken.** ngrok is installed but has no token on this machine. Run `ngrok config add-authtoken <token>` then `ngrok http 8000`, and set `ALLOWED_ORIGIN` in `.env` to the ngrok URL before `docker compose up -d`. |

## 2. Logins

Passwords are in your local `.env` (gitignored), never in code. `make seed` (and the container on every start) sets them from these variables.

| Role | Email | Password variable |
| --- | --- | --- |
| Auditor / admin | admin@example.com | `SEED_ADMIN_PASSWORD` |
| Credit officer, Nilavu Community Credit | officer@example.com | `SEED_OFFICER_PASSWORD` |
| Worker with no data (for the upload demo) | worker@example.com | `SEED_WORKER_PASSWORD` |
| 24 generated workers | e.g. karthik.subramanian@example.com, meena.sundaram@example.com, suresh.kumar@example.com, ganesh.pillai@example.com (all in `backend/app/sim/generate.py`, `NAMED`) | `SEED_WORKER_PASSWORD` |

Statements for the upload demo (generated, fictional): `frontend/e2e/fixtures/bank_statement.csv`, `swiggy_payouts.csv`, `rapido_payouts.csv`.

## 3. Four-minute presentation script (matches what the app does)

1. **Consent (20 s).** Sign in as worker@example.com. *Consents* → give consent for bank statements, then for platform payout statements. Point out purpose, scope, 90-day expiry and *Revoke*.
2. **Upload and reconcile (40 s).** *Sources* → upload `bank_statement.csv`, then `swiggy_payouts.csv` (platform Swiggy) and `rapido_payouts.csv` (platform Rapido). Show "rows read / skipped / duplicates". Scroll to *Transactions*: a bank credit tagged **Matched** to a Swiggy payout, and an **Own transfer** that is not counted.
3. **Passport (40 s).** *My Passport*: score, band, confidence, safe weekly EMI. The seasonality chart title states the raw swing vs the unexplained swing after seasonality is removed. Click a pillar to open the transactions behind it. Switch the language to தமிழ், press *Read aloud*.
4. **Share and officer decision (60 s).** *Share* with Nilavu Community Credit. Sign in as officer@example.com → open the application. Click the *Capacity* pillar → transactions; click *Payouts matched to bank* → each bank credit next to its platform payout. *Suggested loan shape*: weekly EMI collected on the usual payout day, plus a seasonal skip-week. Choose *Modify*, reason code `ADD_SKIP_WEEK`, a note → *Record decision*. (Leaving the reason code empty is refused.)
5. **Thin file (30 s).** In the queue, Suresh Kumar (3 months, one bank account) is **Low confidence → Manual review required**, not declined. Sign in as suresh.kumar@example.com: the passport says "Not enough data yet — add: …" and shows no band verdict.
6. **Recourse (30 s).** Sign in as meena.sundaram@example.com → *How to improve*: one tested step re-scored by the real scoring function moves her from **Band B to Band A**. Nothing suggests more hours or more platforms. (Among the generated workers, Imran Khan has a Band C → B step, but his confidence is Low, so his band is not shown as a verdict.)
7. **Auditor (20 s).** Sign in as admin@example.com → *Validation* (approval uplift vs the bureau-style baseline, calibration by band, "About these results"), *Fairness* (group gaps, proxy check), *Override log* (the decision from step 4 appears as an override of the "approve" suggestion if the requested EMI fit the safe EMI).

Optional extra: officer → *Portfolio* → *Run monthly refresh*: Ganesh Pillai's bad-week floor fell 52% after a 10-week illness → early warning with a *restructure* suggestion.

## 4. What is real vs generated

See [`REAL_VS_GENERATED.md`](REAL_VS_GENERATED.md) (one page) and the provenance table in the README. In short: all computation and every workflow is real; the pre-loaded people, statements, lenders and past decisions are generated; validation numbers are simulated; Account Aggregator and the Gemini language model are not connected (no credentials were provided).

## 5. Known issues and limitations

- **No public URL yet** (section 1): needs your GitHub push for Render or an ngrok authtoken.
- **Gemini not active**: no `GEMINI_API_KEY` was provided, so all explanations use the templates. The provider and its number post-check are built and tested.
- **Account Aggregator**: interface only (`backend/app/ingest/aa.py`); no Setu credentials.
- **Freelancers paid in lumps** score low (Band D/E) under the specified weekly formulas, and simulated vendors never defaulted. Both are reported, not tuned.
- **Long platform histories are often routed to manual review** because one payout without a matching bank credit is enough to raise a flag.
- **Tamil and Hindi** strings were written by the developer and need native-speaker review: `frontend/src/i18n/ta.ts`, `hi.ts`, `backend/app/i18n/templates.py`.
- **Not built** (allowed cuts, BUILD.md section 12): DiCE (the constrained search is the recourse implementation); dark mode.
- **Render free plan**: data written by users is lost on restart.
- Building the image takes about 10 minutes because it generates the dataset and runs the 5,000-worker simulation.

## 6. Commit and push with your own identity

The repo has `.claude/settings.json` with attribution switched off. `.env`, `backend/data/`, `node_modules/`, `dist/` and test outputs are gitignored.

```bash
cd D:/projects/earnscore
git init
git config user.name  "Your Name"
git config user.email "you@example.com"
git add .
git status                      # check that .env and backend/data are NOT listed
git commit -m "EarnScore: alternative creditworthiness for gig workers"
git log --format=full           # confirm there is no Co-Authored-By line
git branch -M main
git remote add origin https://github.com/<your-account>/earnscore.git
git push -u origin main
```

After pushing: Render dashboard → *New* → *Blueprint* → pick the repo → fill `ALLOWED_ORIGIN` and the `SEED_*` values → deploy. Then run `E2E_BASE_URL=https://<your-service>.onrender.com npx playwright test` from `frontend/` to verify production (it reads the officer login from `.env` or the environment).
