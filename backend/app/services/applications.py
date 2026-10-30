"""Share links, applications, officer decisions, overrides and the monthly refresh with early warnings."""
from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, Decision, EarlyWarning, Lender, Override, ShareLink, Snapshot, User, utcnow
from app.schemas import DECISION_REASON_CODES
from app.scoring import loan
from app.scoring.engine import routing
from app.services import snapshots
from app.services.audit import audit

EARLY_WARNING_DROP = 0.20
RESTRUCTURE_DROP = 0.40


def suggested_outcome(route: dict, requested_emi: float, safe_emi: float) -> str:
    if route["reasons"]:
        return "review"
    return "approve" if requested_emi <= safe_emi else "modify"


def loan_suggestion(db: Session, app: Application) -> dict:
    snap = app.snapshot
    user = app.user
    seasonal = snapshots.seasonal_index_for(db, user, snap)
    from app.models import LedgerEntry
    dates = [d for (d,) in db.execute(select(LedgerEntry.date).where(LedgerEntry.user_id == user.id, LedgerEntry.counted.is_(True),
                                                                      LedgerEntry.date <= snap.as_of)).all()]
    start = snap.as_of + timedelta(days=7 - snap.as_of.weekday())
    return loan.suggest(snap.safe_emi, app.requested_amount, app.requested_tenure_weeks, app.lender.annual_rate,
                        dates, seasonal, start)


def create(db: Session, user: User, lender_id: int, days: int, amount: float, tenure: int, purpose: str, ip: str = "",
           as_of=None, created_at=None) -> Application:
    lender = db.get(Lender, lender_id)
    if not lender or not lender.is_active:
        raise HTTPException(404, "Lender not found.")
    snap = snapshots.create_snapshot(db, user, as_of=as_of, alpha=lender.alpha, kind="application", reuse=False)
    if snap is None:
        raise HTTPException(409, "Add at least one statement before sharing your passport.")
    now = created_at or utcnow()
    link = ShareLink(user_id=user.id, lender_id=lender.id, token=secrets.token_urlsafe(24), created_at=now,
                     expires_at=now + timedelta(days=days))
    db.add(link)
    db.flush()
    route = routing(snap.band, snap.confidence, snap.flags)
    requested_emi = loan.emi_for(amount, tenure, lender.annual_rate)
    app = Application(user_id=user.id, lender_id=lender.id, share_link_id=link.id, snapshot_id=snap.id,
                      requested_amount=amount, requested_tenure_weeks=tenure, purpose=purpose, status=route["status"],
                      routing_reasons=route["reasons"], suggested_outcome=suggested_outcome(route, requested_emi, snap.safe_emi),
                      created_at=now)
    db.add(app)
    db.flush()
    audit(db, user.id, "share.create", "share_link", link.id, {"lender_id": lender.id, "days": days, "application_id": app.id}, ip)
    return app


def revoke_share(db: Session, link: ShareLink, actor_id: int, ip: str = "") -> None:
    link.revoked_at = utcnow()
    audit(db, actor_id, "share.revoke", "share_link", link.id, {}, ip)


def officer_can_read(app: Application, officer: User) -> None:
    if officer.role != "officer" or officer.lender_id != app.lender_id:
        raise HTTPException(403, "This application belongs to another lender.")
    if not app.share_link.is_valid():
        raise HTTPException(410, "The worker's share link has expired or was revoked, so this report is no longer available.")


def decide(db: Session, app: Application, officer: User, body, ip: str = "") -> Decision:
    if body.reason_code not in DECISION_REASON_CODES[body.outcome]:
        raise HTTPException(422, "Choose a reason code that fits this decision.")
    if app.status in {"approved", "modified", "declined"}:
        raise HTTPException(409, "A decision has already been recorded for this application.")
    sugg = suggested_outcome({"reasons": app.routing_reasons}, loan.emi_for(app.requested_amount, app.requested_tenure_weeks,
                                                                           app.lender.annual_rate), app.snapshot.safe_emi)
    agrees = sugg == "review" or sugg == body.outcome
    if body.outcome == "modify" and not (body.weekly_emi and body.tenure_weeks and body.amount):
        raise HTTPException(422, "A modified offer needs the weekly EMI, tenure and amount.")
    shape = loan_suggestion(db, app)
    d = Decision(application_id=app.id, officer_id=officer.id, outcome=body.outcome, reason_code=body.reason_code,
                 note=body.note.strip(), agrees_with_suggestion=agrees, payout_day=shape["payout_day"],
                 weekly_emi=body.weekly_emi if body.outcome == "modify" else (shape["requested_emi"] if body.outcome == "approve" else None),
                 tenure_weeks=body.tenure_weeks if body.outcome == "modify" else (app.requested_tenure_weeks if body.outcome == "approve" else None),
                 amount=body.amount if body.outcome == "modify" else (app.requested_amount if body.outcome == "approve" else None),
                 skip_weeks=body.skip_weeks if body.outcome != "decline" else [])
    db.add(d)
    db.flush()
    if not agrees:
        db.add(Override(decision_id=d.id, application_id=app.id, officer_id=officer.id, suggested=sugg, chosen=body.outcome,
                        reason_code=body.reason_code, note=body.note.strip()))
    app.status = {"approve": "approved", "modify": "modified", "decline": "declined"}[body.outcome]
    app.decided_at = utcnow()
    audit(db, officer.id, "decision.record", "application", app.id,
          {"outcome": body.outcome, "reason_code": body.reason_code, "suggested": sugg, "override": not agrees}, ip)
    return d


def refresh_portfolio(db: Session, officer: User, ip: str = "") -> dict:
    apps = db.scalars(select(Application).where(Application.lender_id == officer.lender_id,
                                                Application.status.in_(["approved", "modified"]))).all()
    results = []
    for app in apps:
        # previous snapshot = the latest refresh after the application, else the application's own snapshot
        prev = db.scalar(select(Snapshot).where(Snapshot.user_id == app.user_id, Snapshot.kind == "refresh",
                                                Snapshot.id > app.snapshot_id).order_by(Snapshot.id.desc()).limit(1)) or app.snapshot
        new = snapshots.create_snapshot(db, app.user, alpha=app.lender.alpha, kind="refresh")
        if new is None:
            continue
        drop = (prev.f20 - new.f20) / prev.f20 if prev.f20 > 0 and new.id != prev.id else 0.0
        alert = drop > EARLY_WARNING_DROP
        suggestion = None
        if alert:
            suggestion = "restructure" if drop > RESTRUCTURE_DROP else "skip_week"
            exists = db.scalar(select(EarlyWarning).where(EarlyWarning.application_id == app.id,
                                                          EarlyWarning.new_snapshot_id == new.id))
            if not exists:
                db.add(EarlyWarning(application_id=app.id, prev_snapshot_id=prev.id, new_snapshot_id=new.id,
                                    f20_prev=prev.f20, f20_new=new.f20, drop_pct=round(drop, 4), suggestion=suggestion))
        results.append({"application_id": app.id, "worker": app.user.name, "f20_prev": prev.f20, "f20_new": new.f20,
                        "drop_pct": round(drop, 4), "alert": alert, "suggestion": suggestion, "as_of": new.as_of.isoformat()})
    audit(db, officer.id, "portfolio.refresh", "lender", officer.lender_id, {"applications": len(apps)}, ip)
    db.flush()
    return {"results": results, "ran_at": utcnow().isoformat()}
