"""Deterministic generator (DATA_SOURCES.md section 3).

Writes generated bank and platform statements as files in several realistic formats, then ingests them
through the same upload pipeline a user's file goes through (pipeline.store_upload). Nothing derived
is written directly: scores, bands and EMIs are computed afterwards by the scoring engine.

All people, accounts, banks and phone numbers here are fictional. Platform names are labels only.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest import pipeline
from app.models import Dispute, Lender, User, WorkerProfile, utcnow
from app.services import applications as apps_svc
from app.services import cohort, consent as consent_svc, model_registry, snapshots
from app.sim.life import CITIES, END_DATE, WORK_TYPES, Life, live, make_persona

log = logging.getLogger("earnscore.generate")
SEED = 20261030
GEN_DOMAIN = "example.com"  # reserved domain: generated accounts can never belong to a real person

BANKS = ["Pallava Bank", "Vijayanagar Bank", "Konark Bank", "Satpura Bank"]
LENDERS = [
    {"name": "Nilavu Community Credit", "alpha": 0.5, "annual_rate": 0.22, "default_tenure_weeks": 52,
     "grievance_email": "grievance@nilavu-credit.example.com"},
    {"name": "Prakriti Gig Finance", "alpha": 0.45, "annual_rate": 0.26, "default_tenure_weeks": 40,
     "grievance_email": "grievance@prakriti-finance.example.com"},
]
HISTORIC_OFFICER = {"email": f"r.lakshmi.officer@{GEN_DOMAIN}", "name": "R. Lakshmi"}

# name, city, work type, months, accounts, accounts uploaded, platform statements?, scenario flags, group, apply
NAMED = [
    ("Anitha Raman", "Chennai", "home_service", 24, 2, 2, True, set(), "woman", "approved"),
    ("Karthik Subramanian", "Chennai", "rider", 24, 2, 2, True, set(), "man", "approved"),
    ("Selvi Murugan", "Madurai", "vendor", 18, 2, 2, False, set(), "woman", "pending"),
    ("Mohammed Irfan", "Hyderabad", "rider", 14, 2, 2, True, set(), "man", "modified"),
    ("Priya Nair", "Bengaluru", "freelancer", 20, 2, 2, False, set(), "woman", ""),
    ("Ramesh Gowda", "Bengaluru", "rider", 12, 2, 1, True, set(), "man", "pending"),
    ("Lakshmi Devi", "Coimbatore", "home_service", 10, 1, 1, True, set(), "woman", "pending"),
    ("Arjun Mehta", "Mumbai", "freelancer", 6, 1, 1, False, set(), "man", ""),
    ("Fatima Shaikh", "Mumbai", "vendor", 16, 2, 2, False, set(), "woman", ""),
    ("Suresh Kumar", "Delhi", "rider", 3, 1, 1, False, set(), "man", "pending"),
    ("Deepa Krishnan", "Chennai", "freelancer", 24, 3, 3, False, set(), "woman", ""),
    ("Vijay Anand", "Coimbatore", "rider", 20, 2, 2, True, {"round_trip"}, "man", "pending"),
    ("Kavya Reddy", "Hyderabad", "home_service", 15, 2, 2, True, set(), "woman", ""),
    ("Rajesh Yadav", "Delhi", "vendor", 22, 2, 2, False, set(), "man", ""),
    ("Meena Sundaram", "Madurai", "home_service", 8, 1, 1, True, set(), "woman", ""),
    ("Imran Khan", "Bengaluru", "vendor", 4, 1, 1, False, set(), "man", ""),
    ("Pooja Sharma", "Delhi", "home_service", 12, 2, 2, True, set(), "woman", ""),
    ("Ganesh Pillai", "Mumbai", "rider", 24, 2, 2, True, {"recent_shock"}, "man", "approved"),
    ("Nandini Iyer", "Bengaluru", "freelancer", 11, 2, 2, False, set(), "woman", ""),
    ("Babu Rajan", "Chennai", "vendor", 13, 2, 2, False, {"large_recent_credit"}, "man", "pending"),
    ("Sunita Patil", "Mumbai", "home_service", 19, 2, 2, True, set(), "woman", ""),
    ("Aravind Kumar", "Madurai", "rider", 9, 1, 1, True, set(), "man", ""),
    ("Revathi Balan", "Coimbatore", "vendor", 2, 1, 1, False, set(), "woman", ""),
    ("Harish Chandra", "Hyderabad", "freelancer", 17, 2, 2, False, {"recent_shock"}, "man", ""),
]


def email_for(name: str) -> str:
    return ".".join(name.lower().split()) + f"@{GEN_DOMAIN}"


def fictional_phone(i: int) -> str:
    return f"+91 10000 {i:05d}"  # Indian mobile numbers never start with 1


def money(v: float) -> str:
    return f"{v:,.2f}"


# ---------------------------------------------------------------- statement formats

def bank_csv_pallava(life: Life, acct: int, acct_no: str) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Pallava Bank - Statement of Account"])
    w.writerow(["Account Name", life.persona.name.upper()])
    w.writerow(["Account Number", acct_no])
    w.writerow(["Period", life.start.strftime("%d/%m/%Y"), "to", life.end.strftime("%d/%m/%Y")])
    w.writerow([])
    w.writerow(["Txn Date", "Value Date", "Description", "Ref No./Cheque No.", "Debit", "Credit", "Balance"])
    for t in life.txns:
        if t.account != acct:
            continue
        d = t.date.strftime("%d/%m/%Y")
        w.writerow([d, d, t.narration, t.ref, money(t.amount) if t.direction == "debit" else "",
                    money(t.amount) if t.direction == "credit" else "", money(t.balance)])
    w.writerow(["", "", "Closing Balance", "", "", "", ""])
    return out.getvalue().encode()


def bank_csv_vijayanagar(life: Life, acct: int, acct_no: str) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"])
    for t in life.txns:
        if t.account != acct:
            continue
        d = t.date.strftime("%d-%m-%y")
        w.writerow([d, t.narration, t.ref, d, f"{t.amount:.2f}" if t.direction == "debit" else "",
                    f"{t.amount:.2f}" if t.direction == "credit" else "", f"{t.balance:.2f}"])
    return out.getvalue().encode()


def bank_csv_konark(life: Life, acct: int, acct_no: str) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Konark Bank", f"A/c {acct_no}"])
    w.writerow(["Transaction Date", "Particulars", "Amount (INR)", "Dr/Cr", "Balance (INR)"])
    for t in life.txns:
        if t.account != acct:
            continue
        w.writerow([t.date.isoformat(), t.narration, f"{t.amount:.2f}", "DR" if t.direction == "debit" else "CR", f"{t.balance:.2f}"])
    return out.getvalue().encode()


def bank_xlsx_satpura(life: Life, acct: int, acct_no: str) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"
    ws.append(["Satpura Bank"])
    ws.append([f"Account {acct_no}", life.persona.name])
    ws.append(["Tran Date", "Remarks", "Debit", "Credit", "Balance"])
    for t in life.txns:
        if t.account != acct:
            continue
        ws.append([t.date.strftime("%d/%m/%Y"), t.narration, t.amount if t.direction == "debit" else None,
                   t.amount if t.direction == "credit" else None, t.balance])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def bank_pdf_pallava(life: Life, acct: int, acct_no: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, "Pallava Bank - Statement of Account", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=8)
    pdf.cell(0, 6, f"Account {acct_no}  {life.persona.name.upper()}", new_x="LMARGIN", new_y="NEXT")
    with pdf.table(col_widths=(22, 92, 24, 24, 28), text_align=("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT")) as table:
        table.row(["Date", "Description", "Debit", "Credit", "Balance"])
        for t in life.txns:
            if t.account != acct:
                continue
            table.row([t.date.strftime("%d/%m/%Y"), t.narration[:60], money(t.amount) if t.direction == "debit" else "",
                       money(t.amount) if t.direction == "credit" else "", money(t.balance)])
    return bytes(pdf.output())


def payout_csv(life: Life, platform: str) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    unit = "Jobs" if platform == "Urban Company" else "Trips"
    w.writerow(["Payout Date", "Platform", "Payout Reference", unit, "Active Hours", "Payout Amount"])
    for r in life.payouts:
        if r.platform == platform:
            w.writerow([r.date.isoformat(), r.platform, r.ref, r.trips, f"{r.hours:.1f}", f"{r.amount:.2f}"])
    return out.getvalue().encode()


BANK_FORMATS = [("csv", bank_csv_pallava), ("csv", bank_csv_vijayanagar), ("csv", bank_csv_konark), ("xlsx", bank_xlsx_satpura)]


def account_no(p, a: int) -> str:
    return f"9999 0000 {(p.idx * 37 + a * 1013) % 10000:04d}"  # 9999 0000 prefix: not a real account range


# ---------------------------------------------------------------- ingestion through the upload path

def ingest_life(db: Session, user: User, life: Life, out_dir: Path, accounts_uploaded: int, platform_statements: bool,
                fmt_offset: int, pdf_first: bool = False) -> None:
    bank_consent = consent_svc.grant(db, user.id, "bank_statement", "income_assessment", 365)
    folder = out_dir / f"{user.id:05d}"
    folder.mkdir(parents=True, exist_ok=True)
    for a in range(accounts_uploaded):
        acct_no = account_no(life.persona, a)
        bank = BANKS[(fmt_offset + a) % len(BANKS)]
        if pdf_first and a == 0:
            ext, data = "pdf", bank_pdf_pallava(life, a, acct_no)
            bank = "Pallava Bank"
        else:
            ext, fn = BANK_FORMATS[(fmt_offset + a) % len(BANK_FORMATS)]
            data = fn(life, a, acct_no)
        name = f"{bank.split()[0].lower()}_statement_{acct_no[-4:]}.{ext}"
        (folder / name).write_bytes(data)
        src = pipeline.store_upload(db, user, bank_consent, "bank_statement", name, data, label=f"{bank} ••{acct_no[-4:]}",
                                    institution=bank, account_ref=acct_no[-4:], rebuild=False)
        if src.status != "processed":
            raise RuntimeError(f"generated statement did not parse: {name}: {src.status} {src.error}")
    if platform_statements and life.persona.platforms:
        plat_consent = consent_svc.grant(db, user.id, "platform_statement", "income_assessment", 365)
        for plat in life.persona.platforms:
            data = payout_csv(life, plat)
            name = f"{plat.lower().replace(' ', '_')}_payouts.csv"
            (folder / name).write_bytes(data)
            src = pipeline.store_upload(db, user, plat_consent, "platform_statement", name, data,
                                        label=f"{plat} payouts", platform=plat, rebuild=False)
            if src.status != "processed":
                raise RuntimeError(f"generated payout statement did not parse: {name}: {src.status} {src.error}")
    pipeline.rebuild_ledger(db, user.id)  # one rebuild after all of this worker's uploads (same result)


def ensure_lenders(db: Session) -> list[Lender]:
    out = []
    for spec in LENDERS:
        l = db.scalar(select(Lender).where(Lender.name == spec["name"]))
        if not l:
            l = Lender(**spec)
            db.add(l)
            db.flush()
        out.append(l)
    return out


def generate(db: Session, out_dir: Path, cohort_size: int = 21, named: bool = True) -> dict:
    """Create the 24 named worker accounts, the cohort population and the generated loan history."""
    rng = np.random.default_rng(SEED)
    model_registry.ensure_v1(db)
    lenders = ensure_lenders(db)
    stats = {"named": 0, "cohort": 0}

    # cohort population: generated workers (no login) whose weekly series feed the cohort seasonality index
    n = 0
    for ci, city in enumerate(CITIES):
        for wi, wt in enumerate(WORK_TYPES):
            for k in range(cohort_size):
                n += 1
                email = f"cohort-{n:04d}@{GEN_DOMAIN}"
                if db.scalar(select(User.id).where(User.email == email)):
                    continue
                weeks = int(rng.integers(52, 79))
                accts = 1 if rng.random() < 0.5 else 2
                p = make_persona(rng, 1000 + n, f"Cohort Member {n:04d}", city, wt, weeks, accts)
                life = live(p, seed=SEED + 1000 + n)
                u = User(email=email, name=p.name, role="worker", can_login=False, password_hash=None)
                u.profile = WorkerProfile(city=city, work_type=wt, languages=["en"], phone=fictional_phone(1000 + n))
                db.add(u)
                db.flush()
                ingest_life(db, u, life, out_dir, accts, True, fmt_offset=n)
                stats["cohort"] += 1
            db.commit()
            log.info("cohort generated", extra={"action": f"{city}/{wt}"})
    cohort.recompute(db)
    db.commit()

    if not named:
        return stats
    officer = db.scalar(select(User).where(User.email == HISTORIC_OFFICER["email"]))
    if not officer:
        officer = User(email=HISTORIC_OFFICER["email"], name=HISTORIC_OFFICER["name"], role="officer",
                       lender_id=lenders[0].id, can_login=False)
        db.add(officer)
        db.flush()
    for i, (name, city, wt, months, accts, uploaded, plat, flags, group, apply) in enumerate(NAMED):
        email = email_for(name)
        if db.scalar(select(User.id).where(User.email == email)):
            continue
        weeks = max(8, round(months * 4.345)) + 2  # +2: whole weeks at both ends, so 24 months gives 104 complete weeks (STL)
        p = make_persona(np.random.default_rng(SEED + i), i + 1, name, city, wt, weeks, accts, group=group, flags=set(flags))
        life = live(p, seed=SEED + i)
        u = User(email=email, name=name, role="worker", can_login=True, password_hash=None,
                 preferred_language="ta" if city in {"Chennai", "Coimbatore", "Madurai"} and i % 2 == 0 else
                 ("hi" if city == "Delhi" else "en"))
        langs = ["ta", "en"] if city in {"Chennai", "Coimbatore", "Madurai"} else (["hi", "en"] if city in {"Delhi", "Mumbai"} else ["en"])
        u.profile = WorkerProfile(city=city, work_type=wt, languages=langs, phone=fictional_phone(i + 1),
                                  group_attr=group, group_attr_consent=i % 3 != 2)
        db.add(u)
        db.flush()
        ingest_life(db, u, life, out_dir, uploaded, plat, fmt_offset=i, pdf_first=(i % 6 == 4))
        cohort.recompute(db, city, wt)
        snapshots.current(db, u)
        stats["named"] += 1
        if apply:
            _history(db, u, apply, lenders, officer, i)
        db.commit()
    _disputes(db)
    db.commit()
    return stats


def _history(db: Session, user: User, kind: str, lenders: list[Lender], officer: User, i: int) -> None:
    """Generated application history: older approved loans (for portfolio monitoring) and pending applications."""
    end = snapshots.data_end(db, user.id)
    lender = lenders[0] if i % 4 != 3 else lenders[1]
    if kind == "pending":
        app = apps_svc.create(db, user, lender.id, 90, 30000 + 5000 * (i % 5), 52, "Working capital")
        return
    as_of = end - timedelta(days=70)
    created = utcnow() - timedelta(days=63)
    app = apps_svc.create(db, user, lenders[0].id, 365, 25000 + 5000 * (i % 3), 52, "Two-wheeler repair and working capital",
                          as_of=as_of, created_at=created)
    shape = apps_svc.loan_suggestion(db, app)

    class Body:  # same shape as DecisionIn
        pass

    b = Body()
    # Generated officer policy, applied to the computed report (never to a preset outcome):
    # follow the suggestion; on a manual-review case offer the safe loan shape if there is capacity, else decline.
    b.weekly_emi = b.tenure_weeks = b.amount = None
    b.skip_weeks = shape["skip_weeks"]
    if app.suggested_outcome == "approve":
        b.outcome, b.reason_code = "approve", "CAPACITY_SUFFICIENT"
        b.note = "Bad-week income covers essentials and the EMI; income verified across sources."
    elif shape["weekly_emi"] > 0:
        b.outcome, b.reason_code = "modify", "REDUCE_EMI_TO_SAFE_LEVEL"
        b.note = "Offered the weekly EMI at the safe level with the seasonal skip-week."
        b.weekly_emi, b.tenure_weeks, b.amount = shape["weekly_emi"], shape["tenure_weeks"], shape["amount"]
    else:
        b.outcome, b.reason_code = "decline", "INSUFFICIENT_CAPACITY"
        b.note = "Bad-week income does not cover essentials, so no weekly EMI is safe now."
        b.skip_weeks = []
    apps_svc.decide(db, app, officer, b)
    app.decided_at = created + timedelta(days=2)
    for d in app.decisions:
        d.created_at = created + timedelta(days=2)


def _disputes(db: Session) -> None:
    u = db.scalar(select(User).where(User.email == email_for("Suresh Kumar")))
    if u and not db.scalar(select(Dispute.id).where(Dispute.user_id == u.id)):
        from app.models import Application
        a = db.scalar(select(Application).where(Application.user_id == u.id))
        db.add(Dispute(user_id=u.id, application_id=a.id if a else None, category="data",
                       description="Most of my earnings are cash jobs that are not in this bank account. "
                                   "I can add my second account statement.", updated_at=utcnow()))
