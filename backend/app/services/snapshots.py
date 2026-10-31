"""Build scoring inputs from the reconciled ledger, run the active model and store snapshots."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.classify import payer_of
from app.models import CohortSeasonality, LedgerEntry, PillarScore, ReasonCode, Snapshot, Source, User, WeeklySeries
from app.scoring import config as C
from app.scoring import engine
from app.services import model_registry

BILL_CATEGORIES = {"rent", "utilities", "emi"}
ESSENTIAL_CATEGORIES = {"rent", "utilities", "fuel", "emi"}


def stream_key(e: LedgerEntry) -> str:
    if e.platform:
        return e.platform
    if e.category == "customer_payment":
        return "Direct customer payments"
    return payer_of(e.narration) or "Other income"


def payee_key(narration: str) -> str:
    words = re.sub(r"[^A-Z ]", " ", narration.upper()).split()
    return " ".join(w for w in words if w not in {"UPI", "DR", "NEFT", "IMPS", "ACH", "NACH", "BBPS", "BILLPAY"})[:24]


def cohort_for(db: Session, city: str, work_type: str) -> tuple[dict[int, float] | None, int]:
    rows = db.scalars(select(CohortSeasonality).where(CohortSeasonality.city == city,
                                                      CohortSeasonality.work_type == work_type)).all()
    if not rows:
        return None, 0
    return {r.week_of_year: r.index for r in rows}, rows[0].n_workers


def active_sources(db: Session, user_id: int) -> list[Source]:
    return list(db.scalars(select(Source).where(Source.user_id == user_id, Source.status == "processed")).all())


def data_end(db: Session, user_id: int) -> date | None:
    srcs = [s.id for s in active_sources(db, user_id)]
    if not srcs:
        return None
    return db.scalar(select(LedgerEntry.date).where(LedgerEntry.source_id.in_(srcs)).order_by(LedgerEntry.date.desc()).limit(1))


def build_input(db: Session, user: User, as_of: date) -> tuple[engine.ScoringInput, str]:
    srcs = active_sources(db, user.id)
    src_ids = [s.id for s in srcs]
    entries = db.scalars(select(LedgerEntry).where(LedgerEntry.source_id.in_(src_ids), LedgerEntry.date <= as_of)
                         .order_by(LedgerEntry.date, LedgerEntry.id)).all() if src_ids else []
    weekly = db.scalars(select(WeeklySeries).where(WeeklySeries.user_id == user.id, WeeklySeries.week <= as_of)
                        .order_by(WeeklySeries.week)).all()
    city = user.profile.city if user.profile else ""
    wt = user.profile.work_type if user.profile else ""
    cidx, cn = cohort_for(db, city, wt)
    E = engine.Event
    inp = engine.ScoringInput(as_of=as_of, weeks=[w.week for w in weekly], earned=[w.earned for w in weekly],
                              hours=[w.active_hours for w in weekly], first_date=entries[0].date if entries else None,
                              n_sources=len(srcs), cohort_index=cidx, cohort_n=cn)
    h = hashlib.sha256()
    for e in entries:
        h.update(f"{e.id}|{e.date}|{e.amount}|{e.kind}|{e.category}|{e.counted}|{e.match_status}|{e.balance}|{e.active_hours};".encode())
        if e.counted:
            inp.income.append(E(e.id, e.date, e.amount, key=stream_key(e)))
        if e.direction == "debit" and e.kind == "expense":
            inp.spend.append(E(e.id, e.date, e.amount, category=e.category))
            if e.category in ESSENTIAL_CATEGORIES:
                inp.essentials.append(E(e.id, e.date, e.amount, category=e.category))
            if e.category in BILL_CATEGORIES:
                inp.bills.append(E(e.id, e.date, e.amount, key=payee_key(e.narration), category=e.category))
            if e.category == "bounce":
                inp.bounces.append(E(e.id, e.date, e.amount))
        if e.direction == "debit" and e.category == "savings":
            inp.savings.append(E(e.id, e.date, e.amount))
        if e.source_kind == "bank_statement" and e.balance is not None:
            inp.balances.append(E(e.id, e.date, e.amount, source_id=e.source_id, balance=e.balance))
        if e.source_kind == "platform_statement" and e.direction == "credit":
            inp.payouts.append(E(e.id, e.date, e.amount, key=e.platform, matched=e.match_status == "matched", hours=e.active_hours))
        for fl in e.flags or []:
            inp.flagged.append(E(e.id, e.date, e.amount, flag=fl))
        if e.source_kind == "bank_statement" and e.direction == "credit" and e.kind in {"earned", "other"} \
                and e.category not in {"interest"}:
            inp.large_credits.append(E(e.id, e.date, e.amount))
    h.update(json.dumps({"as_of": as_of.isoformat(), "cfg": C.CONFIG_VERSION, "cohort": cidx, "cn": cn,
                         "weekly": [(w.week.isoformat(), w.earned, w.active_hours) for w in weekly]}, sort_keys=True).encode())
    return inp, h.hexdigest()


def create_snapshot(db: Session, user: User, as_of: date | None = None, alpha: float = C.DEFAULT_ALPHA,
                    kind: str = "on_demand", reuse: bool = True) -> Snapshot | None:
    as_of = as_of or data_end(db, user.id)
    if as_of is None:
        return None
    mv = model_registry.active(db)
    inp, input_hash = build_input(db, user, as_of)
    if reuse:
        prev = db.scalar(select(Snapshot).where(Snapshot.user_id == user.id, Snapshot.input_hash == input_hash,
                                                Snapshot.model_version == mv.version, Snapshot.alpha == alpha,
                                                Snapshot.as_of == as_of).order_by(Snapshot.id.desc()).limit(1))
        if prev:
            return prev
    out = engine.run(inp, alpha=alpha)
    score, band = model_registry.score(mv, out)
    snap = Snapshot(user_id=user.id, as_of=as_of, kind=kind, model_version=mv.version, input_hash=input_hash,
                    score=score, band=band, confidence=out["confidence"], dsi=out["dsi"]["dsi"],
                    dsi_parts=out["dsi"], safe_emi=out["emi"]["safe_emi"], alpha=alpha, f20=out["features"]["f20"],
                    e_ess=out["features"]["e_ess"], features=_jsonable(out["features"]), flags=out["flags"],
                    watchouts=out["watchouts"], seasonality_method=out["features"]["seasonality_method"],
                    series=out["series"], reconciliation=reconciliation_summary(db, user.id, as_of),
                    source_ids=[s.id for s in active_sources(db, user.id)])
    for p, pd_ in out["pillars"].items():
        snap.pillars.append(PillarScore(pillar=p, score=pd_["score"], weight=pd_["weight"],
                                        contribution=pd_["contribution"], components=pd_["components"]))
    for r in out["reasons"]:
        snap.reasons.append(ReasonCode(code=r["code"], pillar=r["pillar"], direction=r["direction"], impact=r["impact"],
                                       params=r["params"] | {"sub": r["sub"]}, evidence_ids=r["evidence_ids"]))
    db.add(snap)
    db.flush()
    return snap


def _jsonable(d: dict) -> dict:
    return json.loads(json.dumps(d, default=float))


def reconciliation_summary(db: Session, user_id: int, as_of: date) -> dict:
    src_ids = [s.id for s in active_sources(db, user_id)]
    rows = db.execute(select(LedgerEntry.source_kind, LedgerEntry.direction, LedgerEntry.kind, LedgerEntry.match_status,
                             LedgerEntry.counted, LedgerEntry.flags, LedgerEntry.amount)
                      .where(LedgerEntry.source_id.in_(src_ids), LedgerEntry.date <= as_of)).all() if src_ids else []
    s = {"payouts": 0, "matched": 0, "unmatched_payouts": 0, "bank_only_income": 0, "self_transfers_excluded": 0,
         "refunds_excluded": 0, "loans_excluded": 0, "flagged_credits": 0, "earned_total": 0.0, "excluded_total": 0.0}
    for kind_src, direction, kind, ms, counted, flags, amount in rows:
        if kind_src == "platform_statement" and direction == "credit":
            s["payouts"] += 1
            if ms == "matched":
                s["matched"] += 1
            elif ms == "unmatched_payout":
                s["unmatched_payouts"] += 1
            continue
        if direction != "credit":
            continue
        if counted:
            s["earned_total"] += amount
            if ms == "bank_only":
                s["bank_only_income"] += 1
        else:
            s["excluded_total"] += amount
        if kind == "self_transfer":
            s["self_transfers_excluded"] += 1
        elif kind == "refund":
            s["refunds_excluded"] += 1
        elif kind == "loan":
            s["loans_excluded"] += 1
        if flags:
            s["flagged_credits"] += 1
    s["earned_total"] = round(s["earned_total"], 2)
    s["excluded_total"] = round(s["excluded_total"], 2)
    return s


def month_ends_before(as_of: date, n: int) -> list[date]:
    out, d = [], as_of.replace(day=1) - timedelta(days=1)
    for _ in range(n):
        out.append(d)
        d = d.replace(day=1) - timedelta(days=1)
    return sorted(out)


def ensure_monthly(db: Session, user: User, as_of: date, months: int = 6) -> None:
    """Score the worker at each of the previous month-ends (trend over time) if not already stored."""
    first = db.scalar(select(LedgerEntry.date).where(LedgerEntry.user_id == user.id).order_by(LedgerEntry.date).limit(1))
    if first is None:
        return
    mv = model_registry.active(db)
    have = set(db.scalars(select(Snapshot.as_of).where(Snapshot.user_id == user.id, Snapshot.kind == "monthly",
                                                       Snapshot.model_version == mv.version)).all())
    for d in month_ends_before(as_of, months):
        if d in have or (d - first).days < 56:
            continue
        create_snapshot(db, user, as_of=d, kind="monthly", reuse=False)


def current(db: Session, user: User, alpha: float = C.DEFAULT_ALPHA) -> Snapshot | None:
    snap = create_snapshot(db, user, alpha=alpha)
    if snap:
        ensure_monthly(db, user, snap.as_of)
    db.commit()
    return snap


def seasonal_index_for(db: Session, user: User, snap: Snapshot) -> dict[int, float] | None:
    """Seasonal index used for the skip-week: the worker's own STL seasonal if available, else the cohort index."""
    if snap.seasonality_method == "stl" and snap.series.get("weeks"):
        mean = (sum(snap.series["raw"]) / len(snap.series["raw"])) or 1.0
        idx = {}
        for w, s in zip(snap.series["weeks"], snap.series["seasonal"]):
            idx[date.fromisoformat(w).isocalendar()[1]] = 1.0 + s / mean
        return idx
    cidx, n = cohort_for(db, user.profile.city if user.profile else "", user.profile.work_type if user.profile else "")
    return cidx if n >= C.COHORT_MIN_WORKERS else None
