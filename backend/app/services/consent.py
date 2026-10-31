"""Consent lifecycle (DPDP-minded): purpose + scope + expiry; revoke removes access now and schedules deletion."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingest.pipeline import delete_source, rebuild_ledger
from app.models import Application, Consent, ShareLink, Snapshot, Source, utcnow
from app.services.audit import audit

SCOPES = {
    "bank_statement": "Transactions in the bank statements you upload: date, narration, debit, credit, balance. "
                      "Used to find earned income, essentials and payment habits.",
    "platform_statement": "Payout statements you upload: payout date, amount, trips or tasks, active hours, platform, "
                          "payout reference. Used to verify income against bank credits.",
    "account_aggregator": "Bank account data shared through the Account Aggregator network with a lender you choose, "
                          "for the period you approve in your AA app.",
}
PURPOSES = {
    "income_assessment": "Build my Earnings Passport",
    "loan_application": "Share my report with a lender I choose for a loan application",
    "monitoring": "Monthly refresh while a loan is active",
}


def consent_out(c: Consent) -> dict:
    now = utcnow()
    status = "revoked" if c.revoked_at else ("expired" if c.expires_at <= now else "active")
    return {"id": c.id, "source_kind": c.source_kind, "purpose": c.purpose, "purpose_text": PURPOSES.get(c.purpose, c.purpose),
            "scope": c.scope, "granted_at": c.granted_at.isoformat(), "expires_at": c.expires_at.isoformat(),
            "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None, "status": status}


def grant(db: Session, user_id: int, source_kind: str, purpose: str, days: int | None = None, ip: str = "") -> Consent:
    days = days or get_settings().consent_default_days
    c = Consent(user_id=user_id, source_kind=source_kind, purpose=purpose, scope=SCOPES[source_kind],
                expires_at=utcnow() + timedelta(days=days))
    db.add(c)
    db.flush()
    audit(db, user_id, "consent.grant", "consent", c.id, {"source_kind": source_kind, "purpose": purpose, "days": days}, ip)
    return c


def _close_share_links(db: Session, consent: Consent, source_ids: set[int], actor_id: int | None, ip: str = "") -> int:
    """Close every open share link whose report was scored on data from these sources."""
    if not source_ids:
        return 0
    now = utcnow()
    rows = db.execute(select(ShareLink, Snapshot.source_ids).join(Application, Application.share_link_id == ShareLink.id)
                      .join(Snapshot, Snapshot.id == Application.snapshot_id)
                      .where(ShareLink.user_id == consent.user_id, ShareLink.revoked_at.is_(None),
                             ShareLink.expires_at > now)).all()
    n = 0
    for link, used in rows:
        if source_ids & set(used or []):
            link.revoked_at = now
            audit(db, actor_id, "share.revoke", "share_link", link.id,
                  {"reason": "consent_withdrawn", "consent_id": consent.id}, ip)
            n += 1
    return n


def _withdraw_sources(db: Session, consent: Consent, actor_id: int | None = None, ip: str = "") -> tuple[int, int]:
    """Withdraw the consent's sources and close share links that include their data. Returns (sources, links)."""
    due = utcnow() + timedelta(days=get_settings().consent_purge_days)
    ids = set()
    for s in db.scalars(select(Source).where(Source.consent_id == consent.id, Source.status != "revoked")).all():
        s.status = "revoked"
        s.delete_after = due
        ids.add(s.id)
    db.flush()
    if ids:
        rebuild_ledger(db, consent.user_id)
    return len(ids), _close_share_links(db, consent, ids, actor_id, ip)


def revoke(db: Session, consent: Consent, actor_id: int, ip: str = "") -> tuple[int, int]:
    consent.revoked_at = utcnow()
    n, links = _withdraw_sources(db, consent, actor_id, ip)
    audit(db, actor_id, "consent.revoke", "consent", consent.id, {"sources_withdrawn": n, "share_links_closed": links}, ip)
    return n, links


def purge_due(db: Session) -> dict:
    """Withdraw sources whose consent expired, and delete sources whose scheduled deletion time has passed."""
    now = utcnow()
    expired = db.scalars(select(Consent).where(Consent.revoked_at.is_(None), Consent.expires_at <= now)).all()
    withdrawn = sum(_withdraw_sources(db, c)[0] for c in expired)
    due = db.scalars(select(Source).where(Source.status == "revoked", Source.delete_after.is_not(None),
                                          Source.delete_after <= now)).all()
    for s in due:
        audit(db, None, "source.purge", "source", s.id, {"user_id": s.user_id})
        delete_source(db, s)
    db.commit()
    return {"withdrawn": withdrawn, "deleted": len(due)}
