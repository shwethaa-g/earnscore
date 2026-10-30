from collections import defaultdict

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import admin_only, client_ip
from app.core.security import PASSWORD_RULE, hash_password, password_ok
from app.models import (Application, AuditLog, Decision, Lender, ModelVersion, Override, PillarScore, SimRun, Snapshot,
                        User, WorkerProfile)
from app.schemas import LenderIn, StaffIn, UserAdminIn
from app.services import cohort, model_registry
from app.services.audit import audit

router = APIRouter(prefix="/admin", tags=["admin"])
PILLARS = list(model_registry.PILLARS)


@router.get("/models")
def models(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    model_registry.ensure_v1(db)
    db.commit()
    rows = db.scalars(select(ModelVersion).order_by(ModelVersion.id)).all()
    return {"models": [{"version": m.version, "kind": m.kind, "is_active": m.is_active, "features": m.features,
                        "weights": m.weights, "training_data": m.training_data, "metrics": m.metrics, "notes": m.notes,
                        "validated": m.validated, "created_at": m.created_at.isoformat()} for m in rows]}


@router.post("/models/{version}/activate")
def activate(version: str, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    target = db.scalar(select(ModelVersion).where(ModelVersion.version == version))
    if not target:
        raise HTTPException(404, "Model version not found.")
    model_registry.activate(db, version)
    audit(db, admin.id, "model.activate", "model_version", version, {"validated": target.validated}, client_ip(request))
    db.commit()
    return {"active": version}


def _latest_run(db: Session) -> SimRun | None:
    return db.scalar(select(SimRun).order_by(SimRun.id.desc()).limit(1))


@router.get("/validation")
def validation(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    r = _latest_run(db)
    if not r:
        return {"run": None}
    return {"run": {"id": r.id, "created_at": r.created_at.isoformat(), "params": r.params, "metrics": r.metrics,
                    "calibration": r.calibration, "recourse": r.recourse, "model_comparison": r.model_comparison,
                    "duration_s": r.duration_s}}


@router.get("/fairness")
def fairness(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    r = _latest_run(db)
    rows = db.execute(select(WorkerProfile.group_attr, Application.status, Snapshot.band)
                      .join(Application, Application.user_id == WorkerProfile.user_id)
                      .join(Snapshot, Snapshot.id == Application.snapshot_id)
                      .where(WorkerProfile.group_attr_consent.is_(True), WorkerProfile.group_attr.is_not(None))).all()
    live = defaultdict(lambda: {"applications": 0, "approved": 0, "declined": 0, "pending": 0})
    for g, status, band in rows:
        x = live[g]
        x["applications"] += 1
        if status in {"approved", "modified"}:
            x["approved"] += 1
        elif status == "declined":
            x["declined"] += 1
        else:
            x["pending"] += 1
    consented = db.scalar(select(func.count()).select_from(WorkerProfile).where(WorkerProfile.group_attr_consent.is_(True)))
    return {"simulated": r.fairness if r else None, "live": dict(live), "live_consented_workers": consented,
            "proxy_note_inputs": ["consistency", "stability", "capacity", "discipline", "resilience"]}


def _psi(a: list[float], b: list[float], bins: int = 10) -> float:
    edges = np.linspace(0, 100, bins + 1)
    pa = np.histogram(a, edges)[0] / max(len(a), 1) + 1e-4
    pb = np.histogram(b, edges)[0] / max(len(b), 1) + 1e-4
    return float(np.sum((pb - pa) * np.log(pb / pa)))


@router.get("/drift")
def drift(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    months = db.scalars(select(Snapshot.as_of).where(Snapshot.kind == "monthly").group_by(Snapshot.as_of)
                        .having(func.count() >= 5).order_by(Snapshot.as_of.desc()).limit(2)).all()
    if len(months) < 2:
        return {"comparison": None}
    newer, older = months[0], months[1]
    data = {m: defaultdict(list) for m in (newer, older)}
    for as_of, pillar, score in db.execute(select(Snapshot.as_of, PillarScore.pillar, PillarScore.score)
                                           .join(PillarScore, PillarScore.snapshot_id == Snapshot.id)
                                           .where(Snapshot.kind == "monthly", Snapshot.as_of.in_([newer, older]))).all():
        data[as_of][pillar].append(score)
    totals = {m: [s for (s,) in db.execute(select(Snapshot.score).where(Snapshot.kind == "monthly", Snapshot.as_of == m)).all()]
              for m in (newer, older)}
    out = []
    for p in PILLARS + ["score"]:
        a = totals[older] if p == "score" else data[older][p]
        b = totals[newer] if p == "score" else data[newer][p]
        psi = _psi(a, b)
        out.append({"feature": p, "psi": round(psi, 4), "mean_prev": round(float(np.mean(a)), 2) if a else None,
                    "mean_new": round(float(np.mean(b)), 2) if b else None, "n_prev": len(a), "n_new": len(b),
                    "status": "stable" if psi < 0.1 else ("watch" if psi < 0.25 else "shifted")})
    return {"comparison": {"previous": older.isoformat(), "current": newer.isoformat(), "features": out}}


@router.get("/overrides")
def overrides(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Decision).order_by(Decision.created_at.desc())).all()
    ov = {o.decision_id: o for o in db.scalars(select(Override)).all()}
    return {"decisions": [{"id": d.id, "application_id": d.application_id, "worker": d.application.user.name,
                           "lender": d.application.lender.name, "officer": d.officer.name, "outcome": d.outcome,
                           "reason_code": d.reason_code, "note": d.note, "suggested": ov[d.id].suggested if d.id in ov else d.application.suggested_outcome,
                           "override": d.id in ov, "band": d.application.snapshot.band,
                           "confidence": d.application.snapshot.confidence, "created_at": d.created_at.isoformat()}
                          for d in rows]}


@router.get("/audit")
def audit_log(action: str | None = None, page: int = Query(1, ge=1), _: User = Depends(admin_only), db: Session = Depends(get_db)):
    q = select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.actor_id)
    if action:
        q = q.where(AuditLog.action.like(f"{action}%"))
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.execute(q.order_by(AuditLog.id.desc()).offset((page - 1) * 50).limit(50)).all()
    actions = [a for (a,) in db.execute(select(AuditLog.action).distinct().order_by(AuditLog.action)).all()]
    return {"rows": [{"id": a.id, "ts": a.ts.isoformat(), "actor": name or "system", "action": a.action,
                      "target": f"{a.target_type}:{a.target_id}" if a.target_type else "", "details": a.details, "ip": a.ip}
                     for a, name in rows], "total": total, "page": page, "page_size": 50, "actions": actions}


@router.get("/users")
def users(role: str | None = None, q: str | None = None, page: int = Query(1, ge=1),
          _: User = Depends(admin_only), db: Session = Depends(get_db)):
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if q:
        query = query.where((User.name.ilike(f"%{q}%")) | (User.email.ilike(f"%{q}%")))
    query = query.where(User.can_login.is_(True))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(User.role, User.name).offset((page - 1) * 50).limit(50)).all()
    return {"users": [{"id": u.id, "email": u.email, "name": u.name, "role": u.role, "is_active": u.is_active,
                       "lender": u.lender.name if u.lender else None, "lender_id": u.lender_id,
                       "city": u.profile.city if u.profile else None, "created_at": u.created_at.isoformat()} for u in rows],
            "total": total, "page": page, "page_size": 50}


@router.post("/users", status_code=201)
def create_staff(body: StaffIn, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if not password_ok(body.password):
        raise HTTPException(422, PASSWORD_RULE)
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "An account with this email already exists.")
    if body.role == "officer" and not (body.lender_id and db.get(Lender, body.lender_id)):
        raise HTTPException(422, "Choose the lender this officer works for.")
    u = User(email=body.email.lower(), name=body.name.strip(), role=body.role, password_hash=hash_password(body.password),
             lender_id=body.lender_id if body.role == "officer" else None)
    db.add(u)
    db.flush()
    audit(db, admin.id, "user.create", "user", u.id, {"role": body.role}, client_ip(request))
    db.commit()
    return {"id": u.id}


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserAdminIn, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found.")
    if u.id == admin.id and body.is_active is False:
        raise HTTPException(422, "You cannot deactivate your own account.")
    changes = body.model_dump(exclude_none=True)
    if "is_active" in changes:
        u.is_active = body.is_active
    if "lender_id" in changes:
        if not db.get(Lender, body.lender_id):
            raise HTTPException(422, "Lender not found.")
        u.lender_id = body.lender_id
    if "role" in changes and body.role != u.role:
        if u.role == "worker" or body.role == "worker":
            raise HTTPException(422, "Worker accounts cannot be converted to staff accounts (or back).")
        u.role = body.role
    audit(db, admin.id, "user.update", "user", u.id, changes, client_ip(request))
    db.commit()
    return {"ok": True}


def lender_out(l: Lender, db: Session) -> dict:
    n = db.scalar(select(func.count()).select_from(Application).where(Application.lender_id == l.id))
    return {"id": l.id, "name": l.name, "alpha": l.alpha, "annual_rate": l.annual_rate,
            "default_tenure_weeks": l.default_tenure_weeks, "grievance_email": l.grievance_email,
            "is_active": l.is_active, "applications": n}


@router.get("/lenders")
def lenders(_: User = Depends(admin_only), db: Session = Depends(get_db)):
    return {"lenders": [lender_out(l, db) for l in db.scalars(select(Lender).order_by(Lender.name)).all()]}


@router.post("/lenders", status_code=201)
def create_lender(body: LenderIn, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    if db.scalar(select(Lender).where(Lender.name == body.name.strip())):
        raise HTTPException(409, "A lender with this name already exists.")
    l = Lender(name=body.name.strip(), alpha=body.alpha, annual_rate=body.annual_rate,
               default_tenure_weeks=body.default_tenure_weeks, grievance_email=body.grievance_email or "")
    db.add(l)
    db.flush()
    audit(db, admin.id, "lender.create", "lender", l.id, body.model_dump(mode="json"), client_ip(request))
    db.commit()
    return lender_out(l, db)


@router.put("/lenders/{lender_id}")
def update_lender(lender_id: int, body: LenderIn, request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    l = db.get(Lender, lender_id)
    if not l:
        raise HTTPException(404, "Lender not found.")
    l.name, l.alpha, l.annual_rate = body.name.strip(), body.alpha, body.annual_rate
    l.default_tenure_weeks, l.grievance_email = body.default_tenure_weeks, body.grievance_email or ""
    audit(db, admin.id, "lender.update", "lender", l.id, body.model_dump(mode="json"), client_ip(request))
    db.commit()
    return lender_out(l, db)


@router.post("/cohorts/recompute")
def recompute_cohorts(request: Request, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    out = cohort.recompute(db)
    audit(db, admin.id, "cohort.recompute", "cohort_seasonality", "all", {"cohorts": len(out)}, client_ip(request))
    db.commit()
    return {"cohorts": out}
