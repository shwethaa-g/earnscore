# PROJECT.md — EarnScore

Alternative creditworthiness for gig workers. RAISE hackathon, Problem Statement 2. Context for Claude Code and for the team.

## 1. Problem statement (PS2)

Gig workers, freelancers, delivery partners, independent service providers and small vendors may earn consistently but receive fragmented payments across several platforms and bank accounts. Traditional credit assessment relies on salary records, employer relationships and conventional credit histories, so people with real earning capacity look financially invisible. A software layer must convert dispersed income signals into a transparent, interpretable profile of earning consistency and repayment capacity.

Expected solution: a platform that securely aggregates (or simulates) income from several sources, cleans and normalises it, and produces an alternative creditworthiness assessment. It emphasises income consistency, stability and cash-flow patterns rather than high income; gives an understandable lender-facing report that explains the main scoring factors; and keeps a responsible-AI design with human review rather than an opaque automated decision.

## 2. Understanding

The problem is not a lack of income but a lack of **legible** income.

- India: about 12 million gig workers in FY25 (up 55% from 7.7 million in FY21), projected 23.5 million by 2029-30. About 40% earn under ₹15,000 a month. The Economic Survey says income volatility hinders credit access and asks for products designed around irregular incomes.
- Root causes: fragmentation across apps, accounts and UPI; no payslip; thin or no bureau file; models that read seasonal swings as risk; scorers that reward raw income though high earnings can signal burnout.
- Three false lender assumptions we correct: volatile ≠ risky (most swings are seasonal); no data ≠ bad (it means unknown); more income ≠ safer (the bad-week floor predicts repayment; 80-hour weeks are a risk).
- Users: gig workers, freelancers, vendors; credit officers at NBFCs, cooperative banks, MFIs; platforms; regulators.
- Constraints: RBI Digital Lending Directions 2025 (express consent, minimal data, India storage, grievance officer), DPDP Act 2023, RBI FREE-AI framework (humans hold final authority; understandable by design), Account Aggregator rules (only regulated entities can be FIUs; EarnScore acts as technology provider to the lender).

## 3. Existing solutions and their gaps

| Existing | What it does | Gap |
| --- | --- | --- |
| TransUnion CIBIL CreditVision NTC | Bureau score for new-to-credit | Lender-facing; no gig cash flow; data sources undisclosed |
| Perfios, FinBox BankConnect | Bank statement analytics | One account at a time; no platform earnings; FinBox's own research says no single source verifies gig income |
| FinBox DeviceConnect (FIS) | Device-data score | Privacy concerns; no worker-side explanation |
| Kaleidofin ki score | B2B informal-sector scoring API | Lender-only; no mention of contest; farmer/MFI focus |
| GigID / GigScore (2026 pilot claim) | Worker-held 300–900 score from earnings, ratings, ITR | Method and validation undisclosed; scores earnings (rewards income size); no reconciliation, seasonality, sufficiency, human review |
| KarmaLife | Platform-data eligibility for short loans | Tied to partner platforms; not portable |
| BillMart GigCash | Earnings-linked credit line | Single lender; criteria not explained |
| Swiggy/Ola platform credit | Repaid from platform earnings | One platform; lock-in |
| RBI Innovation Hub × Vivifi pilot | Unsecured gig loans with alternative data | Pilot; confirms demand; EarnScore can plug in via ULI |
| Argyle (US), Prism CashScore (US) | Platform income verification; cash-flow score | US market; no worker recourse |
| Hackathon/open projects: Monnai GigScore, MicroCredit AI, CredMate, FinFlow, migrant-worker study | Notebook/mock scorers | Synthetic data, no validation, label circularity, some use SMS/location/peer ratings |

Research behind the design: FinRegLab (cash-flow data predicts repayment), Di Maggio et al. "Invisible Primes" (traditional models make such borrowers 70% more likely to be rejected), JPMorgan Chase Institute (income volatility and platform income), CGAP "Putting Gig Data to Work" (fragmentation, burnout, churn; KarmaLife 90% on-time repayment), Fuster et al. "Predictably Unequal?" (flexible ML can widen gaps), Ustun et al. "Actionable Recourse", Mothilal et al. DiCE, InterpretML.

## 4. Solution

A worker-owned **Earnings Passport** plus an explainable **lender report**. The credit officer decides.

Flow: consent per source → connect (AA via lender; statement upload) → reconcile into one ledger (each rupee counted once; self-transfers, refunds, loans labelled) → weekly series with seasonality removed → five pillars → EarnScore 0–100, band A–E, confidence, safe weekly EMI → worker sees reasons and steps; lender sees evidence-linked report → officer approves/modifies/declines with reason code → monthly refresh and early warning.

Pillars: Consistency 25%, Stability 25% (unexplained volatility only), Capacity 25% (share of bad-week income left after essentials), Discipline 15%, Resilience 10%. Income size is never scored. Safe EMI = 0.5 × (bad-week income − essentials). Data Sufficiency is a separate index that sets confidence. Band D/E, Low confidence, or anti-gaming flags route to manual review; nothing is auto-declined.

Responsible AI: glass-box model (scorecard, then Explainable Boosting Machine with monotonic constraints); LLM only rewrites reason codes and tags ambiguous narrations and cannot change numbers; no protected attributes as inputs; fairness audits; model card; audit log; no SMS, contacts, call logs or location.

## 5. Gaps filled (differentiators)

1. Counts every rupee once (reconciliation across platform and bank).
2. Predictable swings are not punished (seasonality-aware stability; cohort seasonality for short histories).
3. "Unknown" is not "risky" (Data Sufficiency index).
4. Income-size neutral and overwork-aware.
5. Safe EMI sized on the bad week.
6. Evidence-linked lender report (click a factor, see transactions).
7. Safe, tested recourse (never "work more hours").
8. Early warning with relief (skip-week before a missed EMI).
9. Human decides by design, with reason codes and an override log.
10. Privacy-minimal and regulator-ready.
11. Portable passport that suggests a loan shape matching payout day.
12. Honest validation (defaults emerge from simulated cash shortfalls, avoiding label circularity).

## 6. Novelty and innovation

A worker-facing gig score alone is not new (GigID, MicroCredit AI exist). What no product or project we reviewed documents is the combination: reconciliation, seasonality removal, a separate sufficiency signal, income-neutral pillars, bad-week EMI, evidence-linked reports, safe recourse, early-warning relief and mandatory human review.

## 7. Market and impact

- TAM 12M workers (₹180 crore/year in reports at 2 reports × ₹75), SAM 6M (₹90 crore), SOM year 3 300,000 workers (₹4.5 crore; about ₹1,200 crore credit unlocked at ₹40,000 average). These rest on our own assumptions.
- Why now: Account Aggregator scale (2,887M+ accounts enabled; 1,076 FIUs live), RBI Innovation Hub gig-loan pilot with ULI next, planned ₹10,000 microloan for e-Shram gig workers, Swiggy ₹102 crore loans to delivery partners in 12 months, Economic Survey recommendations.
- Business model: free for workers; per-report API fee for lenders; SaaS for cooperative banks and MFIs; platform partnerships for bulk passports.
- Pilot targets (500 workers): ≥ 2× approvals vs bureau-only, ≥ 90% on-time repayment, ≥ 25% move up a band in 3 months, women-vs-men approval gap within 5 points, < 10 minutes consent-to-report. SDGs 1.4, 5, 8.10, 10.
- Risks and mitigations: over-indebtedness (bad-week cap), privacy (consent, no phone data), bias (no protected inputs, audits), gaming (reconciliation checks), platform data access (statement upload fallback), shocks (resilience pillar, early warning).

## 8. Level 3 evaluation criteria and how we answer them

| Criterion | Where it shows |
| --- | --- |
| Overall solution | Full three-role workflow, end to end |
| Implementation | Real parsers, reconciliation, scoring engine, tests, deployment |
| Usability | Mobile-first worker app, vernacular, voice, clear reports |
| Demonstration | Four-minute scripted run through the live site |
| Impact | Pilot targets, validation page, SDG alignment |
| Innovation | Differentiators 1–12 |
| Feasibility | AA/ULI fit, regulatory mapping, honest data provenance, cost model |

## 9. Honest limitations (say them before the jury does)

- Validation is simulated until a real pilot; no claim of real-world accuracy.
- Pre-loaded worker histories are generated, not real people.
- Real AA data needs a regulated lender partner; upload is the working path.
- Platform APIs depend on partnerships.
- Market numbers use our assumptions for price and usage.

## 10. Four-minute presentation script

1. Worker signs in, gives per-source consent (20 s). 2. Upload statements; show a payout matched across app and bank and a self-transfer excluded (40 s). 3. Passport: raw swing vs unexplained swing after seasonality (40 s). 4. Officer opens the report, clicks a pillar to the transactions, approves with a payout-day EMI and a February skip-week (60 s). 5. A thin-file worker gets "not enough data", routed to review, not rejected (30 s). 6. Recourse step re-scored from Band C to B (30 s). 7. Auditor: fairness gaps, validation vs baseline, override log (20 s).

## 11. Links (fill in at the end)

- GitHub repository: _to be added by the team_
- Deployed URL: _to be added by the team_
- Submission and briefing docs: Level 1 submission (3 pages), Jury Briefing and Pitch Guide.
