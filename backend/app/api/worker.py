from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import user_out
from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import client_ip, worker_only
from app.ingest import parsers, pipeline
from app.ingest.classify import PLATFORMS
from app.models import Application, Consent, Dispute, LedgerEntry, ShareLink, Snapshot, Source, User, utcnow
from app.schemas import CategoryIn, ConsentIn, DisputeIn, MappingIn, ProfileIn, ShareIn
from app.services import applications as apps_svc
from app.services import cohort, consent as consent_svc, reports, snapshots
from app.services.audit import audit

router = APIRouter(prefix="/worker", tags=["worker"])


# ---------------- profile

@router.get("/profile")
def get_profile(user: User = Depends(worker_only)):
    return user_out(user)


@router.put("/profile")
def put_profile(body: ProfileIn, request: Request, user: User = Depends(worker_only), db: Session = Depends(get_db)):
    p = user.profile
    cohort_changed = (p.city, p.work_type) != (body.city, body.work_type)
    user.name = body.name.strip()
    user.preferred_language = body.preferred_language
    p.city, p.work_type, p.languages = body.city, body.work_type, list(body.languages)
    p.group_attr_consent = body.group_attr_consent
    p.group_attr = body.group_attr if body.group_attr_consent else None
    p.training_consent = body.training_consent
    audit(db, user.id, "profile.update", "user", user.id, {"cohort_changed": cohort_changed}, client_ip(request))
    db.commit()
    return user_out(user)


# ---------------- consents

@router.get("/consents")
def list_consents(user: User = Depends(worker_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Consent).where(Consent.user_id == user.id).order_by(Consent.granted_at.desc())).all()
    counts = dict(db.execute(select(Source.consent_id, func.count()).where(Source.user_id == user.id)
                             .group_by(Source.consent_id)).all())
    return {"consents": [consent_svc.consent_out(c) | {"sources": counts.get(c.id, 0)} for c in rows],
            "scopes": consent_svc.SCOPES, "purposes": consent_svc.PURPOSES,
            "default_days": get_settings().consent_default_days}


@router.post("/consents", status_code=201)
def create_consent(body: ConsentIn, request: Request, user: User = Depends(worker_only), db: Session = Depends(get_db)):
    c = consent_svc.grant(db, user.id, body.source_kind, body.purpose, body.days, client_ip(request))
    db.commit()
    return consent_svc.consent_out(c)


@router.post("/consents/{consent_id}/revoke")
def revoke_consent(consent_id: int, request: Request, user: User = Depends(worker_only), db: Session = Depends(get_db)):
    c = db.get(Consent, consent_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Consent not found.")
    if c.revoked_at:
        raise HTTPException(409, "This consent is already revoked.")
    n, links = consent_svc.revoke(db, c, user.id, client_ip(request))
    db.commit()
    return consent_svc.consent_out(c) | {"sources_withdrawn": n, "share_links_closed": links}


# ---------------- sources

def source_out(s: Source) -> dict:
    raw = s.raw_files[0] if s.raw_files else None
    return {"id": s.id, "kind": s.kind, "label": s.label, "institution": s.institution, "account_ref": s.account_ref,
            "status": s.status, "parsed_count": s.parsed_count, "skipped_count": s.skipped_count,
            "duplicate_count": s.duplicate_count, "skipped_rows": s.skipped_rows, "error": s.error,
            "created_at": s.created_at.isoformat(), "consent_id": s.consent_id,
            "delete_after": s.delete_after.isoformat() if s.delete_after else None,
            "file": {"name": raw.filename, "type": raw.file_type, "size": raw.size,
                     "mapping_confidence": raw.mapping_confidence} if raw else None}


def _own_source(db: Session, user: User, source_id: int) -> Source:
    s = db.get(Source, source_id)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Source not found.")
    return s


@router.get("/sources")
def list_sources(user: User = Depends(worker_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Source).where(Source.user_id == user.id).order_by(Source.created_at.desc())).all()
    from app.ingest import aa
    return {"sources": [source_out(s) for s in rows], "platforms": PLATFORMS, "aa": aa.status(),
            "max_upload_mb": get_settings().max_upload_mb}


@router.post("/sources", status_code=201)
async def upload_source(request: Request, file: UploadFile = File(...), kind: str = Form(...), consent_id: int = Form(...),
                        label: str = Form(""), institution: str = Form(""), account_ref: str = Form(""),
                        platform: str = Form(""), user: User = Depends(worker_only), db: Session = Depends(get_db)):
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"The file is larger than {get_settings().max_upload_mb} MB.")
    if kind == "platform_statement" and platform and platform not in PLATFORMS:
        raise HTTPException(422, "Choose a platform from the list.")
    consent = db.get(Consent, consent_id)
    try:
        s = pipeline.store_upload(db, user, consent, kind, file.filename or "statement", data, label=label,
                                  institution=institution, account_ref=account_ref, platform=platform)
    except pipeline.IngestError as e:
        raise HTTPException(422, str(e)) from e
    audit(db, user.id, "source.upload", "source", s.id, {"kind": kind, "status": s.status, "parsed": s.parsed_count},
          client_ip(request))
    if s.status == "processed" and user.profile:
        cohort.recompute(db, user.profile.city, user.profile.work_type)
    db.commit()
    return source_out(s)


@router.get("/sources/{source_id}")
def source_detail(source_id: int, user: User = Depends(worker_only), db: Session = Depends(get_db)):
    s = _own_source(db, user, source_id)
    out = source_out(s)
    if s.status in {"needs_mapping", "processed"} and s.raw_files:
        try:
            table = pipeline.load_table(s)
            out["preview"] = parsers.preview(table)
            out["mapping"] = s.raw_files[0].detected_mapping
        except (parsers.ParseError, OSError):
            out["preview"] = None
    return out


@router.post("/sources/{source_id}/mapping")
def apply_mapping(source_id: int, body: MappingIn, request: Request, user: User = Depends(worker_only),
                  db: Session = Depends(get_db)):
    s = _own_source(db, user, source_id)
    if s.status not in {"needs_mapping", "failed", "processed"} or not s.raw_files:
        raise HTTPException(409, "This source cannot be re-mapped.")
    table = pipeline.load_table(s)
    cols = set(table.columns)
    m = body.model_dump()
    for k in ("date", "narration", "debit", "credit", "amount", "balance", "ref"):
        if m.get(k) and m[k] not in cols:
            raise HTTPException(422, f"Column '{m[k]}' is not in this file.")
    if not (m.get("amount") or m.get("debit") or m.get("credit")):
        raise HTTPException(422, "Map either an amount column or debit and credit columns.")
    mapping = {**{k: m.get(k) for k in ("date", "narration", "debit", "credit", "amount", "balance", "ref")},
               "date_format": m["date_format"], "drcr": None, "trips": None, "active_hours": None, "platform": None,
               "default_platform": s.institution if s.kind == "platform_statement" else ""}
    from sqlalchemy import delete
    from app.models import Transaction
    db.execute(delete(LedgerEntry).where(LedgerEntry.source_id == s.id))
    db.execute(delete(Transaction).where(Transaction.source_id == s.id))
    pipeline.process_source(db, s, mapping, table=table)
    audit(db, user.id, "source.map", "source", s.id, {"parsed": s.parsed_count, "skipped": s.skipped_count}, client_ip(request))
    if user.profile:
        cohort.recompute(db, user.profile.city, user.profile.work_type)
    db.commit()
    return source_out(s)


@router.delete("/sources/{source_id}")
def remove_source(source_id: int, request: Request, user: User = Depends(worker_only), db: Session = Depends(get_db)):
    s = _own_source(db, user, source_id)
    audit(db, user.id, "source.delete", "source", s.id, {"kind": s.kind, "label": s.label}, client_ip(request))
    pipeline.delete_source(db, s)
    if user.profile:
        cohort.recompute(db, user.profile.city, user.profile.work_type)
    db.commit()
    return {"ok": True}


# ---------------- ledger (my transactions as classified)

@router.get("/ledger")
def my_ledger(kind: str | None = None, category: str | None = None, page: int = Query(1, ge=1),
              user: User = Depends(worker_only), db: Session = Depends(get_db)):
    q = select(LedgerEntry, Source.label).join(Source, Source.id == LedgerEntry.source_id).where(
        LedgerEntry.user_id == user.id, Source.status == "processed")
    if kind:
        q = q.where(LedgerEntry.kind == kind)
    if category:
        q = q.where(LedgerEntry.category == category)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.execute(q.order_by(LedgerEntry.date.desc(), LedgerEntry.id.desc()).offset((page - 1) * 50).limit(50)).all()
    return {"rows": [reports.ledger_row(le, label) for le, label in rows], "total": total, "page": page, "page_size": 50}


@router.patch("/ledger/{entry_id}/category")
def set_category(entry_id: int, body: CategoryIn, request: Request, user: User = Depends(worker_only),
                 db: Session = Depends(get_db)):
    le = db.get(LedgerEntry, entry_id)
    if not le or le.user_id != user.id:
        raise HTTPException(404, "Entry not found.")
    if le.direction != "debit" or le.source_kind != "bank_statement":
        raise HTTPException(422, "Only bank debits can be re-categorised.")
    old = le.category
    le.kind = "other" if body.category == "savings" else "expense"
    le.category = body.category
    le.tagged_by = "user"
    audit(db, user.id, "ledger.recategorise", "ledger_entry", le.id, {"from": old, "to": body.category}, client_ip(request))
    db.commit()
    return reports.ledger_row(le)


# ---------------- passport

@router.get("/passport")
def passport(lang: str = Query("en", pattern="^(en|ta|hi)$"), user: User = Depends(worker_only), db: Session = Depends(get_db)):
    snap = snapshots.current(db, user)
    if snap is None:
        return {"empty": True}
    return reports.passport_out(db, user, snap, lang)


@router.get("/passport/{snapshot_id}/evidence")
def passport_evidence(snapshot_id: int, reason_id: int | None = None, pillar: str | None = None,
                      user: User = Depends(worker_only), db: Session = Depends(get_db)):
    snap = db.get(Snapshot, snapshot_id)
    if not snap or snap.user_id != user.id:
        raise HTTPException(404, "Report not found.")
    if reason_id:
        return reports.reason_evidence(db, snap, reason_id)
    if pillar:
        return reports.pillar_evidence(db, snap, pillar)
    raise HTTPException(422, "Choose a reason or a pillar.")


@router.get("/recourse")
def recourse(lang: str = Query("en", pattern="^(en|ta|hi)$"), user: User = Depends(worker_only), db: Session = Depends(get_db)):
    snap = snapshots.current(db, user)
    if snap is None:
        return {"empty": True}
    return reports.recourse_out(snap, lang) | {"confidence": snap.confidence, "score": snap.score, "band": snap.band}


# ---------------- shares and applications

def app_out(a: Application) -> dict:
    d = a.decisions[-1] if a.decisions else None
    return {"id": a.id, "lender": a.lender.name, "lender_id": a.lender_id, "status": a.status,
            "requested_amount": a.requested_amount, "requested_tenure_weeks": a.requested_tenure_weeks,
            "purpose": a.purpose, "created_at": a.created_at.isoformat(), "routing_reasons": a.routing_reasons,
            "score": a.snapshot.score, "band": a.snapshot.band, "confidence": a.snapshot.confidence,
            "share": {"id": a.share_link.id, "expires_at": a.share_link.expires_at.isoformat(),
                      "revoked_at": a.share_link.revoked_at.isoformat() if a.share_link.revoked_at else None,
                      "valid": a.share_link.is_valid()},
            "decision": {"outcome": d.outcome, "reason_code": d.reason_code, "note": d.note, "weekly_emi": d.weekly_emi,
                         "tenure_weeks": d.tenure_weeks, "amount": d.amount, "payout_day": d.payout_day,
                         "skip_weeks": d.skip_weeks, "created_at": d.created_at.isoformat()} if d else None}


@router.get("/applications")
def my_applications(user: User = Depends(worker_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Application).where(Application.user_id == user.id).order_by(Application.created_at.desc())).all()
    return {"applications": [app_out(a) for a in rows]}


@router.post("/shares", status_code=201)
def create_share(body: ShareIn, request: Request, user: User = Depends(worker_only), db: Session = Depends(get_db)):
    a = apps_svc.create(db, user, body.lender_id, body.days, body.requested_amount, body.requested_tenure_weeks,
                        body.purpose, client_ip(request))
    db.commit()
    db.refresh(a)
    return app_out(a)


@router.post("/shares/{share_id}/revoke")
def revoke_share(share_id: int, request: Request, user: User = Depends(worker_only), db: Session = Depends(get_db)):
    link = db.get(ShareLink, share_id)
    if not link or link.user_id != user.id:
        raise HTTPException(404, "Share link not found.")
    if link.revoked_at:
        raise HTTPException(409, "This share link is already revoked.")
    apps_svc.revoke_share(db, link, user.id, client_ip(request))
    db.commit()
    return {"ok": True}


# ---------------- disputes

def dispute_out(d: Dispute) -> dict:
    return {"id": d.id, "category": d.category, "description": d.description, "status": d.status, "response": d.response,
            "application_id": d.application_id, "snapshot_id": d.snapshot_id, "created_at": d.created_at.isoformat(),
            "updated_at": d.updated_at.isoformat(), "worker": d.user.name if d.user else ""}


@router.get("/disputes")
def my_disputes(user: User = Depends(worker_only), db: Session = Depends(get_db)):
    rows = db.scalars(select(Dispute).where(Dispute.user_id == user.id).order_by(Dispute.created_at.desc())).all()
    return {"disputes": [dispute_out(d) for d in rows]}


@router.post("/disputes", status_code=201)
def raise_dispute(body: DisputeIn, request: Request, user: User = Depends(worker_only), db: Session = Depends(get_db)):
    if body.application_id:
        a = db.get(Application, body.application_id)
        if not a or a.user_id != user.id:
            raise HTTPException(404, "Application not found.")
    if body.snapshot_id:
        s = db.get(Snapshot, body.snapshot_id)
        if not s or s.user_id != user.id:
            raise HTTPException(404, "Report not found.")
    d = Dispute(user_id=user.id, category=body.category, description=body.description.strip(),
                application_id=body.application_id, snapshot_id=body.snapshot_id, updated_at=utcnow())
    db.add(d)
    db.flush()
    audit(db, user.id, "dispute.raise", "dispute", d.id, {"category": body.category}, client_ip(request))
    db.commit()
    return dispute_out(d)
