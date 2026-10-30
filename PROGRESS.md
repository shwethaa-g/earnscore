# PROGRESS.md — EarnScore build log

Start time: Fri Oct 30 18:32:32 IST 2026 (budget ~6 h → target finish ~00:30 IST)

Resume rule: if context is summarised or the session restarts, re-read PROGRESS.md, BUILD.md and PROMPTS.md and resume at the first unfinished stage. Never redo verified work.

## Stage status

| Stage | Status | Verified |
| --- | --- | --- |
| 0 Questions + setup | done | Questions asked/answered; repo layout, .claude/settings.json, .env.example, Makefile, Dockerfile, docker-compose.yml, render.yaml, /healthz. `docker compose up` verified. |
| 1 Auth, roles, consent, DB | done | 20+ tables, Alembic 0001, bcrypt + JWT httpOnly cookie, CSRF double-submit, rate limit, roles; pytest: auth, roles, CSRF, consent revoke, audit writes |
| 2 Ingestion + reconciliation | done | CSV/XLSX/PDF parsers + mapping, classification, exact reconcile rule, round-trip / large-credit / unmatched flags, dedupe, raw file deletion, AAProvider interface; pytest edge cases |
| 3 Scoring engine | done | pure functions in scoring/engine.py, constants in scoring/config.py; STL/cohort/moving-median; pillars, bands, DSI, EMI, routing, reason codes with evidence ids, snapshots with input hash + model version |
| 4 Generator + simulator | done | 24 named + 588 cohort workers ingested through the upload pipeline (all statements parse); sim_run 1: 5,000 workers, AUC 0.877, KS 0.645, 3.26x approvals at equal default rate; EBM v2 AUC 0.902 vs 0.888 (validated, not auto-activated) |
| 5 Worker experience | done | Playwright: register → consent → upload bank + 2 payout statements → passport/evidence → Tamil switch → share; sweep of all 7 worker pages at 1280/360 px in en, ta, hi (no overflow, no errors) |
| 6 Officer experience | done | Playwright: queue → report → pillar evidence → matched-pair drill-down → mandatory reason code → decision; worker sees it. Portfolio refresh + early warning verified via API; report generation 0.6 s |
| 7 Auditor/admin + model v2 | done | sweep of all 8 admin pages; validation page with "About these results"; model cards; fairness (fairlearn); drift (PSI); override log; audit log; users & lenders |
| 8 Language layer | done | Gemini provider + templates + number post-check; tests prove LLM cannot change numbers/score |
| 9 Quality pass + Playwright | done | Final `make test`: pytest 66 passed, vitest 6 passed, Playwright 9 passed (against the Docker container). Fixed: post-login redirect, logout/401 handling, 360 px overflow (grid min-width, absolutely-positioned sr-only header), SQLite WAL slowdown (19.8 s → 0.3 s upload), chart animation, "0%" reason wording, wording audit |
| 10 Deploy + handover | partly blocked | Docker image builds and runs; README, HANDOVER.md, REAL_VS_GENERATED.md written. Public HTTPS URL blocked on the user's credential (GitHub push for Render, or ngrok authtoken). |

Note: stages were built in a slightly merged order (backend 1–4 + 8 first, then frontend 5–7) because they share code; each stage's verification is listed above.

## Stage 0 answers (from the user)

- Deploy: **Render**, with **ngrok** as backup.
- LLM: **Gemini** (no key given → template fallback active until `GEMINI_API_KEY` is set).
- Setu AA credentials: **No** → `AAProvider` interface + statement upload path only.
- Database: **SQLite**.
- Branding: **Defaults** (EarnScore, "Prove how reliably you earn.", neutral slate palette, one teal accent, Inter).
- Cohorts: **All from spec** (7 cities × 4 work types).
- Platform names: **Real brand names** as labels only (README states no data/partnership).
- Bank format: **No** specific bank; several realistic formats built.

## Decisions (what · why · how to change)

1. **as_of = date of the latest transaction** (not today). Why: a statement ending in June would otherwise show months of "no income". Change: `snapshots.data_end`.
2. **Reconcile rate = matched payouts / platform payouts (last 52 weeks); 0 when no platform statement.** Why: BUILD.md does not define it for bank-only users. Effect: bank-only workers max DSI 0.7 only with 12+ months and 3 sources. Change: `engine.extract_features`.
3. **Moving-median seasonality fallback caps confidence at Medium.** Why: BUILD.md says "mark confidence accordingly". Change: `config.FALLBACK_CONFIDENCE_CAP`.
4. **Sub-metric curves and within-pillar weights** (not specified in BUILD.md) are in `scoring/config.py` (`CURVES`, `SUB_WEIGHTS`). Unmeasurable sub-metrics (no balances, no bills, no hours) score a neutral 50 ("unknown is not bad").
5. **Suggested outcome**: approve if no routing flag and the requested EMI fits the safe EMI; modify if it does not; "review" (no suggestion) when routed to manual review. An override is logged whenever the officer's outcome differs from approve/modify suggestions.
6. **Cohort population**: 588 generated cohort members (21 per city × work type, no login) are ingested through the upload path so the cohort seasonal index has ≥ 20 workers per cohort. Without them every short-history worker would fall back to the moving median.
7. **Generated dataset is baked into the Docker image at build time** (generate + simulate run in `docker build`). Why: Render free has no persistent disk and a slow start. Role-account passwords are still set at container start from env (`start.sh` → `seed`). Change: Dockerfile `RUN` line.
8. **Bureau-style baseline**: a file exists for 70% of workers with an existing loan, 15% otherwise; synthetic bureau score = 780 − 70 × bounced EMIs on that loan + noise (or 650 + noise without a loan); approve ≥ 650. The first version (driven by latent discipline) was near random (AUC 0.50) and would have been a strawman, so it was grounded once in the repayment record a bureau actually sees; not iterated further.
9. **EBM v2 is never auto-activated**; it is marked validated only if held-out AUC beats v1 by > 0.005 and approvals at equal default are not lower. Admin switches models.
10. **Lenders are fictional** ("Nilavu Community Credit", "Prakriti Gig Finance"); banks in generated statements are fictional (Pallava, Vijayanagar, Konark, Satpura); accounts start "9999 0000", phones "+91 10000 …", emails @example.com.
11. **Generated officer "R. Lakshmi"** (no login) made the generated past decisions with a fixed policy applied to computed values (follow suggestion; manual review → safe loan shape if capacity else decline).
12. **Consent purge**: revoke → sources withdrawn immediately, files/rows deleted after `CONSENT_PURGE_DAYS` (7) by an hourly job / `make purge`.

## Honest findings so far

- Freelancers paid in lumps (zero-income weeks between invoices) get F20 = 0 and land in Band D/E under the spec's weekly formulas. Not tuned; reported as a limitation.
- Many long-history platform workers get an `unmatched_payout` flag because the generator mis-pays ~1% of payouts by 3% (outside the 1% tolerance), so they route to manual review. This is the rule working as written.

13. **SQLite PRAGMA synchronous=NORMAL + WAL checkpoint after bulk CLI commands.** Why: a 66 MB un-checkpointed WAL made each insert take 16 ms (uploads took ~20 s). Change: `core/db.py`, `cli.checkpoint`.
14. **"simulated" wording** appears only in the Admin "About these results" panel and the model card's training-data description (DATA_SOURCES.md requires the truth there); elsewhere the UI says "validation run".
15. **Backup public URL**: downloading `cloudflared` (no-account tunnel) was blocked by the permission classifier; ngrok has no authtoken. A public URL needs the user's ngrok token or a Render deploy from their GitHub push.
16. **`/api/auth/session`** returns `{user: null}` when signed out, so the app does not log a 401 on every public page.

17. **Early-warning scenario length**: the generated "recent_shock" scenario (Ganesh Pillai, Harish Chandra) is a 10-week illness ending at the data end. With 7 weeks only 5 complete low weeks fell inside the 26-week window, under the 20th percentile, so F20 hardly moved and no alert fired. This defines the scenario; the alert rule (F20 drop > 20%) is unchanged.

18. **Seasonality fixes found by reviewing real output** (CONFIG_VERSION 2026.10.3): (a) STL on exactly 2 years used a seasonal smoother that fit each week-of-year through both points, so unexplained volatility was ~0 and every swing was excused; now `seasonal_deg=0` (seasonal shape constant across years). (b) The cohort index used a per-week median, which collapsed to ~0 for zero-heavy freelancer cohorts and blew V_res up to 9–10; now a per-week mean, bounded to [0.5, 2.0]. Tests added for both.
19. **Recourse shows one step per feature** (it previously listed "cash buffer" up to three times via different pairs). Test added.
20. **Named workers get +2 weeks of history** so 24-month workers have 104 complete weeks and the STL path is exercised (the last week before the data end is partial).
21. **Cut (BUILD.md section 12)**: DiCE not used (constrained search is the implementation, as allowed); dark mode not built (optional). Nothing on the never-cut list was cut.

## Open items for the user

- ngrok has no authtoken on this machine (`ngrok config add-authtoken <token>` needed for the backup URL).
- Render deploy needs the repo pushed to GitHub by you (I don't push); `render.yaml` is provided.
- `GEMINI_API_KEY` not provided; set it in Render env / `.env` to enable the LLM path.
- Tamil and Hindi strings (frontend/src/i18n/ta.ts, hi.ts; backend/app/i18n/templates.py) were written by me and need review by a native speaker.

## BUILD.md section 13 — checked against the running container (30 Oct, 20:47 IST)

- [x] `docker compose up` starts everything; `make test` passes (66 + 6 + 9); Playwright flow passes.
- [x] All three roles log in and use every page with no dead ends (sweep: 18 pages × 2 widths + worker pages in ta/hi at 360 px).
- [x] A user can upload a bank statement CSV and get a complete report (e2e flow; unknown formats go through the column-mapping step, tested).
- [x] Every number on screen traces to the database; no hardcoded results; no placeholders; wording audit done.
- [x] Hindi/Tamil/English switch works on all worker pages.
- [x] README: setup, env vars, architecture, data provenance, validation results, limitations.
- [ ] Deployed at a single HTTPS URL — needs the user's GitHub push (Render) or ngrok authtoken.
- [x] One-page "what is real vs generated": REAL_VS_GENERATED.md.
