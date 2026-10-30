# DATA_SOURCES.md — where every piece of data comes from

Claude Code: this file is a contract. Implement exactly this, ask me if anything is unclear, and produce the final "real vs generated" table in the README.

## 1. What is real and what is not (be honest, always)

| Item | Status | Source |
| --- | --- | --- |
| Scoring logic, reconciliation, seasonality, pillars, bands, safe EMI | **Real computation** | Code in `backend/app/scoring` and `ingest`, run on whatever data is in the database |
| Login, roles, consent, audit log, share links, disputes, decisions | **Real functionality** | Database writes by actual users |
| Bank statements and platform payout statements uploaded by a user | **Real data path** | The user's own files (CSV/XLSX/PDF). Any genuine statement works. |
| Account Aggregator connection | **Real only if** I provide Setu sandbox/production credentials. Otherwise the `AAProvider` interface exists and the upload path is used. Real AA needs a regulated lender as the data recipient, so a hackathon build cannot use production AA data. | Ask me at Stage 0 |
| Worker accounts and transaction histories pre-loaded for the evaluation | **Generated** | Deterministic generator (section 3). They are not real people or real bank records. |
| Cohort seasonality indices | **Derived** | Computed from the data in the database (generated plus uploaded) |
| Validation results (approval uplift, AUC, fairness gaps) | **Simulated** | Output of the simulator in `BUILD.md` §7. They show how the method behaves under stated assumptions, not real-world accuracy. |
| Market numbers (12M workers, 23.5M, 40% under ₹15,000) | **Cited** | Economic Survey 2025-26, NITI Aayog; used only in README/pitch, not computed |
| Platform names (Swiggy, Zomato, Uber, Rapido, Urban Company) in generated statements | **Labels only** | No data was obtained from these companies and no partnership exists. Use neutral names in the UI if I ask. |

## 2. Rules

1. Nothing derived (scores, bands, EMI, charts, trends) is ever typed into code or the frontend. It is always computed from database rows.
2. The generator uses the same ingestion pipeline as a user upload. No special database back door.
3. The UI does not label data as "demo/sample/mock". The README and the Admin "About these results" panel state the truth about generated data and simulated validation. I will also tell the jury.
4. No real person's data is used. Generated names, phone numbers and account numbers must be clearly fictional (e.g. numbers that cannot be real) and not resemble any real individual.
5. Never scrape websites, platforms or apps for data. Never claim a partnership, regulatory approval or licence that does not exist.
6. Uploaded files and extracted rows belong to the uploading user, can be deleted by them, and are never used to train models without an explicit consent flag.

## 3. The generator (`backend/app/sim/generate.py`)

- Fixed random seed, configurable count (default 5,000 for validation; 24 named worker accounts for logins).
- Personas: delivery rider (2 platforms, weekly payouts, monsoon surge, February dip), home-service professional (lumpy jobs), freelancer (irregular transfers, some foreign-currency credits), vendor (daily UPI collections).
- Each worker gets: 2–3 bank accounts' worth of statements, platform payout statements, rent/utility/fuel debits, own-account transfers, refunds, an occasional loan credit, bounced debits for a few workers, and 2–24 months of history (so Low/Medium/High confidence all occur).
- Cohort seasonality: city (Chennai, Coimbatore, Madurai, Bengaluru, Hyderabad, Mumbai, Delhi) × work type, with festival (Diwali, Pongal, Eid) and monsoon effects plus a yearly dip.
- Shocks: deactivation, illness weeks, vehicle breakdown costs.
- Outcome simulation for validation: a loan with EMI; default only if cash cannot cover the EMI for three consecutive payout cycles.
- Output files are written as CSV/PDF statements in realistic bank formats (several formats, so the parser is genuinely tested), then ingested through the normal upload path.
- Whatever scores the generator produces are what the app shows. Do not tune the generator to hit a specific score. If numbers in `PROJECT.md` examples (e.g. the 72/100 example) differ from the computed output, update the docs.

## 4. Statement format support (parser contract)

- CSV/XLSX: any column order; mapping UI when auto-detection is under 90% confident. Date formats dd/mm/yyyy, dd-mm-yy, yyyy-mm-dd. Debit/credit as two columns or one signed column. UPI narrations (e.g. `UPI/CR/<ref>/<payer>`).
- PDF: text-based bank statements only. Scanned images are out of scope; show a clear message and ask for CSV.
- Platform payout statements: date, payout amount, trips/tasks, active hours (optional), platform name, payout reference.

## 5. Questions Claude must ask me before building data features

1. Do I have Setu AA sandbox credentials?
2. Which cities and work types should the seeded accounts cover?
3. Should platform names appear as real brand names or neutral names in the UI?
4. Any statement format from a real bank I want supported (I can provide an anonymised sample)?
