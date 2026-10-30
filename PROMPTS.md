# PROMPTS.md — prompts for Claude Code (run in order)

Put `BUILD.md`, `PROJECT.md`, `DATA_SOURCES.md` and this file in an empty project folder, open Claude Code there, and paste the Master Prompt. Then paste one stage prompt at a time. Do not start a stage until the previous one is verified.

## Master prompt (paste first)

```
You are building EarnScore, a complete, deployable website, on your own, in this folder.
Read BUILD.md, PROJECT.md and DATA_SOURCES.md fully before doing anything. They are the source of truth.

Rules:
- If anything is unclear, missing, or has more than one reasonable reading, STOP and ask me (use AskUserQuestion). Never assume. Never invent credentials, numbers, regulations or copy.
- Work stage by stage from PROMPTS.md. After each stage, run the tests, start the app, exercise the real endpoints and pages, and fix every failure before moving on. Never weaken a test to pass.
- No placeholders, no dead buttons, no TODOs. The UI must never say demo, sample, mock, test or dummy.
- Never hardcode derived values (scores, bands, EMIs, charts). Compute from the database.
- Do not run git commit or git push and never add Co-Authored-By lines.
- Keep a running STATUS.md with: stages done, what you verified, open questions for me.
Start with Stage 0.
```

## Stage 0 — Questions and setup

```
Stage 0. Before writing code, ask me everything in BUILD.md section 0.2 and DATA_SOURCES.md section 5 in one AskUserQuestion batch (deployment target, LLM provider/key, Setu AA credentials, branding and team name, database, cities/work types, platform naming, sample bank statement format).
Then: scaffold the repo layout from BUILD.md section 2, create .claude/settings.json with the attribution settings from section 11, .env.example, Makefile, Dockerfile, docker-compose.yml, and a health check. Verify `docker compose up` serves a page and /healthz.
Report in STATUS.md and wait for my confirmation.
```

## Stage 1 — Auth, roles, consent, database

```
Stage 1. Implement the data model (BUILD.md section 4) with Alembic migrations, email+password auth with JWT in httpOnly cookies, role-based access (worker, officer, auditor/admin), consent records (purpose, scope, expiry, revoke), audit log, and a `make seed` command that creates role accounts from env vars.
Frontend: login, register (worker), role-based routing, app shell with navigation and language switch scaffold.
Tests: auth, role access, consent revoke, audit writes. Verify manually in the browser for all three roles. Ask me about any unclear field or rule.
```

## Stage 2 — Ingestion and reconciliation

```
Stage 2. Build ingestion per BUILD.md section 5 and DATA_SOURCES.md section 4: CSV/XLSX parsers with column-mapping UI, PDF parser with honest failure messages, platform payout statement parser, classification rules, the exact reconciliation rule (1% / 0–3 days / payer match), anti-gaming flags, raw file storage and deletion, an AAProvider interface (Setu implementation only if I gave credentials).
Frontend: Sources page for upload, mapping, status, counts parsed vs skipped, delete source.
Tests: edge cases for tolerance, window, duplicates, self-transfer, refunds, malformed rows. Create several realistic statement formats yourself for tests. Ask me if you need a real format.
```

## Stage 3 — Scoring engine

```
Stage 3. Implement BUILD.md section 6 as pure, unit-tested functions with constants in scoring/config.py: weekly series, cohort seasonality, STL with fallback, five pillars, EarnScore, bands, Data Sufficiency and confidence, safe EMI, routing rules, reason codes with evidence links, snapshots stored with input hash and model version.
API endpoints for worker passport and officer report. Do not hardcode any output. If any formula is ambiguous, ask me before choosing.
```

## Stage 4 — Generator and validation simulator

```
Stage 4. Implement DATA_SOURCES.md section 3 and BUILD.md sections 7 and 8: the deterministic generator that writes realistic statements in several formats and ingests them through the normal upload path, 24 named logins plus the large validation population, the outcome simulator (default only after three consecutive uncovered EMI cycles), the bureau-style baseline, metrics (approval uplift at equal default rate, AUC, KS, calibration, wrongly rejected share), fairness audit, and recourse feasibility. Store in sim_runs.
Report the real computed results to me honestly, including if they are unimpressive. Do not tune the generator to get a target number.
```

## Stage 5 — Worker experience

```
Stage 5. Build the worker area in BUILD.md section 3: Sources, Consents, Passport with pillars/trend/Data Sufficiency, plain-language reasons, How to improve (constrained recourse search that re-scores with the real function and never suggests hours or platform count), Share links with expiry and revocation, Disputes, English/Tamil/Hindi on every page, read-aloud, mobile-first at 360 px.
Translations must be reviewed by me: list every Tamil and Hindi string in STATUS.md for my check and ask about any phrase you are unsure of.
```

## Stage 6 — Officer experience

```
Stage 6. Build the officer area: applications queue with filters and routing flags, evidence-linked report with drill-down to transactions, reconciliation summary, raw-vs-adjusted seasonality chart, suggested loan shape (weekly EMI on payout day, seasonal skip-week), Approve/Modify/Decline with mandatory reason codes, portfolio monthly refresh with early-warning alerts, disputes inbox. Every lender read of a report writes an audit entry.
```

## Stage 7 — Auditor/admin experience and model v2

```
Stage 7. Build model cards, active-model switch, fairness page, drift page, override log, validation page with an "About these results" panel stating parameters truthfully, user/lender management. Train the EBM on simulator outcomes with monotonic constraints and register it as v2; keep v1 active if v2 does not validate better, and say so in the model card.
```

## Stage 8 — Language layer

```
Stage 8. Implement the provider interface: LLM provider (if I gave a key) for narration tagging and reason-code rewriting, with a deterministic template fallback that is always available. Add the post-check that every number in generated text equals the source value, otherwise fall back to the template. Prove with tests that the LLM output can never change a score. Keep keys server-side only.
```

## Stage 9 — Quality pass

```
Stage 9. Full quality pass: remove every placeholder and the words demo/sample/mock/test/dummy from user-facing text (search the codebase), check empty/loading/error states on every page, accessibility, 360 px layout, security checklist in BUILD.md section 10, performance (report generation under 3 seconds on the seeded data). Write the Playwright end-to-end flow (worker upload → score → share → officer review → decision → worker sees decision) and run the whole suite. Fix everything that fails.
```

## Stage 10 — Deploy and handover

```
Stage 10. Deploy to the target I chose in Stage 0. Run migrations, seed role accounts, run the generator, and verify the live URL end to end with Playwright against production. Write the README (setup, env vars, architecture diagram in text, data provenance table copied from DATA_SOURCES.md section 1, limitations, honest). Produce HANDOVER.md with: live URL, logins for each role, the four-minute presentation script from PROJECT.md adjusted to what the app actually does, a "real vs generated" one-pager, known issues, and the exact git commands for me to commit and push with my own identity. Remind me to confirm `git log --format=full` shows no Co-Authored-By line.
```

## When Claude Code gets stuck

```
Stop. Summarise what failed, what you tried, and the two best options. Ask me which to take. Do not work around a failure by hiding it, mocking it, or lowering a test.
```

## Optional follow-up prompts

- "Re-read BUILD.md section 13 and verify every checkbox against the running app. List any that fail."
- "Search the repository and the rendered pages for the words demo, sample, mock, dummy, test data, TODO, lorem. Fix each hit."
- "Compare the pillars, weights, bands and formulas in code with BUILD.md section 6. List any difference."
- "Ask me five hard jury questions about this app and show how the app answers each one with a real screen."
