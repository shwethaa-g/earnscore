from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.worker import dispute_out
from app.core.db import get_db
from app.core.deps import client_ip, officer_only, officer_or_admin
from app.models import Application, Dispute, EarlyWarning, LedgerEntry, Snapshot, Source, User, utcnow
from app.schemas import DECISION_REASON_CODES, DecisionIn, DisputeUpdateIn
from app.services import applications as apps_svc
from app.services import reports
from app.services.audit import audit

router = APIRouter(prefix="/officer", tags=["officer"])


def queue_row(a: Application) -> dict:
    s = a.snapshot
    return {"id": a.id, "worker": a.user.name, "city": a.user.profile.city if a.user.profile else "",
            "work_type": a.user.profile.work_type if a.user.profile else "", "score": s.score, "band": s.band,
            "confidence": s.confidence, "safe_emi": s.safe_emi, "status": a.status, "routing_reasons": a.routing_reasons,
            "manual_review": a.status == "manual_review_required" or bool(a.routing_reasons),
            "requested_amount": a.requested_amount, "requested_tenure_weeks": a.requested_tenure_weeks,
            "created_at": a.created_at.isoformat(), "share_valid": a.share_link.is_valid(),
            "suggested_outcome": a.suggested_outcome}


@router.get("/applications")
def queue(band: str | None = None, confidence: str | None = None, status: str | None = None,
          manual_review: bool | None = None, officer: User = Depends(officer_only), db: Session = Depends(get_db)):
    q = select(Application).join(Snapshot, Snapshot.id == Application.snapshot_id).where(Application.lender_id == officer.lender_id)
    if band:
        q = q.where(Snapshot.band == band)
    if confidence:
        q = q.where(Snapshot.confidence == confidence)
    if status:
        q = q.where(Application.status == status)
    rows = db.scalars(q.order_by(Application.created_at.desc())).all()
    out = [queue_row(a) for a in rows]
    if manual_review is not None:
        out = [r for r in out if r["manual_review"] == manual_review]
    return {"applications": out, "lender": officer.lender.name if officer.lender else ""}


def _app(db: Session, app_id: int, officer: User) -> Application:
    a = db.get(Application, app_id)
    if not a:
        raise HTTPException(404, "Application not found.")
    apps_svc.officer_can_read(a, officer)
    return a


@router.get("/applications/{app_id}")
def report(app_id: int, request: Request, officer: User = Depends(officer_only), db: Session = Depends(get_db)):
    a = _app(db, app_id, officer)
    snap = a.snapshot
    audit(db, officer.id, "report.read", "application", a.id, {"worker_id": a.user_id, "snapshot_id": snap.id}, client_ip(request))
    db.commit()
    body = reports.passport_out(db, a.user, snap, "en")
    body["trend"] = [t for t in body["trend"] if t["as_of"] <= snap.as_of.isoformat()]
    warnings = db.scalars(select(EarlyWarning).where(EarlyWarning.application_id == a.id).order_by(EarlyWarning.id.desc())).all()
    return body | {
        "application": queue_row(a) | {"purpose": a.purpose},
        "worker": {"name": a.user.name, "city": a.user.profile.city, "work_type": a.user.profile.work_type,
                   "languages": a.user.profile.languages},
        "loan_shape": apps_svc.loan_suggestion(db, a),
        "decisions": [{"outcome": d.outcome, "reason_code": d.reason_code, "note": d.note, "officer": d.officer.name,
                       "weekly_emi": d.weekly_emi, "tenure_weeks": d.tenure_weeks, "amount": d.amount,
                       "skip_weeks": d.skip_weeks, "agrees_with_suggestion": d.agrees_with_suggestion,
                       "created_at": d.created_at.isoformat()} for d in a.decisions],
        "reason_codes": DECISION_REASON_CODES,
        "early_warnings": [{"id": w.id, "f20_prev": w.f20_prev, "f20_new": w.f20_new, "drop_pct": w.drop_pct,
                            "suggestion": w.suggestion, "created_at": w.created_at.isoformat()} for w in warnings],
        "lender": {"name": a.lender.name, "alpha": a.lender.alpha, "annual_rate": a.lender.annual_rate},
    }


@router.get("/applications/{app_id}/evidence")
def evidence(app_id: int, request: Request, reason_id: int | None = None, pillar: str | None = None,
             flag: str | None = None, officer: User = Depends(officer_only), db: Session = Depends(get_db)):
    a = _app(db, app_id, officer)
    snap = a.snapshot
    audit(db, officer.id, "report.evidence_read", "application", a.id,
          {"reason_id": reason_id, "pillar": pillar, "flag": flag}, client_ip(request))
    db.commit()
    if reason_id:
        return reports.reason_evidence(db, snap, reason_id)
    if pillar:
        return reports.pillar_evidence(db, snap, pillar)
    if flag:
        ids = next((f["evidence_ids"] for f in snap.flags if f["flag"] == flag), [])
        return {"flag": flag, "rows": reports.evidence_rows(db, a.user_id, ids)}
    raise HTTPException(422, "Choose a reason, pillar or flag.")


@router.get("/applications/{app_id}/ledger")
def ledger(app_id: int, request: Request, view: str = Query("matched", pattern="^(matched|unmatched|excluded|flagged)$"),
           officer: User = Depends(officer_only), db: Session = Depends(get_db)):
    """Reconciliation drill-down: matched pairs, unmatched payouts, excluded credits or flagged rows."""
    a = _app(db, app_id, officer)
    audit(db, officer.id, "report.ledger_read", "application", a.id, {"view": view}, client_ip(request))
    db.commit()
    q = select(LedgerEntry, Source.label).join(Source, Source.id == LedgerEntry.source_id).where(
        LedgerEntry.user_id == a.user_id, Source.status == "processed", LedgerEntry.date <= a.snapshot.as_of)
    if view == "matched":
        q = q.where(LedgerEntry.match_status == "matched", LedgerEntry.source_kind == "bank_statement")
    elif view == "unmatched":
        q = q.where(LedgerEntry.match_status == "unmatched_payout")
    elif view == "excluded":
        q = q.where(LedgerEntry.direction == "credit", LedgerEntry.counted.is_(False), LedgerEntry.source_kind == "bank_statement")
    rows = db.execute(q.order_by(LedgerEntry.date.desc()).limit(400)).all()
    out = [reports.ledger_row(le, label) for le, label in rows]
    if view == "flagged":
        out = [r for r in out if r["flags"]]
    if view == "matched":
        partner_ids = [r["matched_to"] for r in out if r["matched_to"]]
        partners = {p["id"]: p for p in reports.evidence_rows(db, a.user_id, partner_ids, limit=400)}
        for r in out:
            r["pair"] = partners.get(r["matched_to"])
    return {"view": view, "rows": out}


@router.post("/applications/{app_id}/decision", status_code=201)
def decide(app_id: int, body: DecisionIn, request: Request, officer: User = Depends(officer_only), db: Session = Depends(get_db)):
    a = _app(db, app_id, officer)
    d = apps_svc.decide(db, a, officer, body, client_ip(request))
    db.commit()
    return {"id": d.id, "outcome": d.outcome, "status": a.status, "agrees_with_suggestion": d.agrees_with_suggestion}


@router.get("/portfolio")
def portfolio(officer: User = Depends(officer_only), db: Session = Depends(get_db)):
    apps = db.scalars(select(Application).where(Application.lender_id == officer.lender_id,
                                                Application.status.in_(["approved", "modified"]))
                      .order_by(Application.decided_at.desc())).all()
    out = []
    for a in apps:
        d = a.decisions[-1] if a.decisions else None
        w = db.scalar(select(EarlyWarning).where(EarlyWarning.application_id == a.id).order_by(EarlyWarning.id.desc()).limit(1))
        out.append(queue_row(a) | {
            "weekly_emi": d.weekly_emi if d else None, "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            "warning": {"drop_pct": w.drop_pct, "f20_prev": w.f20_prev, "f20_new": w.f20_new, "suggestion": w.suggestion,
                        "created_at": w.created_at.isoformat(), "status": w.status} if w else None})
    return {"loans": out}


@router.post("/portfolio/refresh")
def refresh(request: Request, officer: User = Depends(officer_only), db: Session = Depends(get_db)):
    res = apps_svc.refresh_portfolio(db, officer, client_ip(request))
    db.commit()
    return res


# ---------------- disputes (grievance officer view)

def _disputes_query(user: User):
    q = select(Dispute)
    if user.role == "officer":
        worker_ids = select(Application.user_id).where(Application.lender_id == user.lender_id)
        q = q.where(or_(Dispute.application_id.in_(select(Application.id).where(Application.lender_id == user.lender_id)),
                        Dispute.user_id.in_(worker_ids)))
    return q


@router.get("/disputes")
def disputes(user: User = Depends(officer_or_admin), db: Session = Depends(get_db)):
    rows = db.scalars(_disputes_query(user).order_by(Dispute.created_at.desc())).all()
    return {"disputes": [dispute_out(d) for d in rows]}


@router.patch("/disputes/{dispute_id}")
def update_dispute(dispute_id: int, body: DisputeUpdateIn, request: Request, user: User = Depends(officer_or_admin),
                   db: Session = Depends(get_db)):
    d = db.scalar(_disputes_query(user).where(Dispute.id == dispute_id))
    if not d:
        raise HTTPException(404, "Dispute not found.")
    if body.status == "resolved" and len(body.response.strip()) < 5:
        raise HTTPException(422, "Write a response to the worker before resolving.")
    d.status, d.response, d.responder_id, d.updated_at = body.status, body.response.strip(), user.id, utcnow()
    audit(db, user.id, "dispute.update", "dispute", d.id, {"status": body.status}, client_ip(request))
    db.commit()
    return dispute_out(d)
