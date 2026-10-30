# EarnScore — what is real and what is generated (one page)

**Short version:** the software is real and runs on whatever data it is given. The people and transactions pre-loaded for the evaluation are generated. The validation numbers come from a simulation. Nothing was obtained from any platform, bank or Account Aggregator.

## Real

| What | Where it comes from |
| --- | --- |
| Statement parsing (CSV, Excel, text PDF), column mapping, duplicate detection | `backend/app/ingest/parsers.py`, `pipeline.py` — works on any genuine statement a user uploads |
| Classification, reconciliation (1% / 0–3 days / payer match), anti-gaming flags | `backend/app/ingest/classify.py`, `reconcile.py` |
| Seasonality, five pillars, score, band, Data Sufficiency, safe EMI, routing, reason codes, recourse, loan shape | `backend/app/scoring/` — computed from database rows every time; nothing is typed in |
| Login, roles, consent (grant / revoke / scheduled deletion), share links, applications, decisions with reason codes, overrides, disputes, audit log | Real database writes by whoever uses the app |
| A user's own uploaded statements | The user's files; deletable by them; never used for training without the training-consent flag |

## Generated (deterministic, seed 20261030)

| What | Notes |
| --- | --- |
| 24 named worker accounts (e.g. Karthik Subramanian, Anitha Raman, Suresh Kumar) | Fictional people. Emails use the reserved `example.com` domain; phones start `+91 10000` (not a valid Indian mobile range) |
| 588 cohort members (no login) | Exist only so the cohort seasonal index has ≥ 20 workers per city × work type |
| Their bank and platform statements | Written as files in five formats by `backend/app/sim/generate.py`, then ingested through the same upload pipeline a user's file goes through. Banks (Pallava, Vijayanagar, Konark, Satpura) are invented; account numbers start `9999 0000` |
| Platform names on generated payouts (Swiggy, Zomato, Uber, Rapido, Urban Company) | Labels only. No data came from these companies and no partnership exists |
| Lenders (Nilavu Community Credit, Prakriti Gig Finance) | Invented |
| Past applications and decisions of generated workers, and the officer "R. Lakshmi" who made them | Generated with a fixed policy applied to the computed reports |
| One open dispute (Suresh Kumar) | Generated |

## Derived

| What | Notes |
| --- | --- |
| Cohort seasonal indices | Learned from all weekly series in the database (generated + uploaded) |
| Monthly score trend, drift (PSI) | Re-scoring the same ledgers at earlier month-ends |

## Simulated

| What | Notes |
| --- | --- |
| Validation: AUC 0.877, KS 0.645, 3.26× approvals vs a bureau-style baseline at equal default rate, calibration by band, recourse feasibility, fairness gaps, EBM v2 comparison | 5,000 simulated workers (`backend/app/sim/simulate.py`). Defaults come only from simulated cash shortfalls (3 consecutive uncovered EMIs). The bureau baseline is synthetic. These numbers show how the method behaves under stated assumptions — **not real-world accuracy** |

## Not connected

| What | Notes |
| --- | --- |
| Account Aggregator (Setu) | No credentials were provided. The `AAProvider` interface exists; the app says AA is opened by a regulated lender and offers statement upload instead |
| Language model (Gemini) | Built and tested, but no API key was provided, so all explanations use the deterministic templates |

## Cited, not computed

Market figures (≈12 M gig workers in FY25, 23.5 M by 2029-30, ≈40% earning under ₹15,000/month) are from the Economic Survey 2025-26 and NITI Aayog, and appear only in the pitch material, not in the app.
