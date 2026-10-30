"""SQLAlchemy models (BUILD.md section 4)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Lender(Base):
    __tablename__ = "lenders"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    alpha: Mapped[float] = mapped_column(Float, default=0.5)
    annual_rate: Mapped[float] = mapped_column(Float, default=0.24)
    default_tenure_weeks: Mapped[int] = mapped_column(Integer, default=52)
    grievance_email: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), index=True)  # worker | officer | admin
    lender_id: Mapped[int | None] = mapped_column(ForeignKey("lenders.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    can_login: Mapped[bool] = mapped_column(Boolean, default=True)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    lender: Mapped[Lender | None] = relationship()
    profile: Mapped[WorkerProfile | None] = relationship(back_populates="user", uselist=False)


class WorkerProfile(Base):
    __tablename__ = "worker_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    city: Mapped[str] = mapped_column(String(60), default="")
    work_type: Mapped[str] = mapped_column(String(30), default="")  # rider | home_service | freelancer | vendor
    languages: Mapped[list] = mapped_column(JSON, default=list)
    phone: Mapped[str] = mapped_column(String(20), default="")
    own_account_refs: Mapped[list] = mapped_column(JSON, default=list)  # masked refs of the worker's own accounts
    group_attr: Mapped[str | None] = mapped_column(String(30), nullable=True)  # audit only, never a model input
    group_attr_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    training_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship(back_populates="profile")


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_kind: Mapped[str] = mapped_column(String(30))  # bank_statement | platform_statement | account_aggregator
    purpose: Mapped[str] = mapped_column(String(60))
    scope: Mapped[str] = mapped_column(Text)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.revoked_at is None and self.expires_at > now


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    consent_id: Mapped[int] = mapped_column(ForeignKey("consents.id"))
    kind: Mapped[str] = mapped_column(String(30))  # bank_statement | platform_statement | account_aggregator
    label: Mapped[str] = mapped_column(String(120))
    institution: Mapped[str] = mapped_column(String(120), default="")
    account_ref: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending")  # needs_mapping | processed | failed | revoked
    parsed_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_rows: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    delete_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consent: Mapped[Consent] = relationship()
    raw_files: Mapped[list[RawFile]] = relationship(back_populates="source", cascade="all, delete-orphan")


class RawFile(Base):
    __tablename__ = "raw_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    stored_path: Mapped[str] = mapped_column(String(400))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    file_type: Mapped[str] = mapped_column(String(10))  # csv | xlsx | pdf
    detected_mapping: Mapped[dict] = mapped_column(JSON, default=dict)
    mapping_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source: Mapped[Source] = relationship(back_populates="raw_files")


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    narration: Mapped[str] = mapped_column(Text, default="")
    direction: Mapped[str] = mapped_column(String(6))  # credit | debit
    amount: Mapped[float] = mapped_column(Float)
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref: Mapped[str] = mapped_column(String(80), default="")
    platform: Mapped[str] = mapped_column(String(60), default="")
    trips: Mapped[int | None] = mapped_column(Integer, nullable=True)
    active_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    row_hash: Mapped[str] = mapped_column(String(64), index=True)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), unique=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    source_kind: Mapped[str] = mapped_column(String(30))
    date: Mapped[date] = mapped_column(Date, index=True)
    week: Mapped[date] = mapped_column(Date, index=True)  # Monday of the ISO week
    direction: Mapped[str] = mapped_column(String(6))
    amount: Mapped[float] = mapped_column(Float)
    narration: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(20))  # earned | self_transfer | refund | loan | expense | other
    category: Mapped[str] = mapped_column(String(30), default="")  # rent | utilities | fuel | emi | savings | bounce | payout | ...
    platform: Mapped[str] = mapped_column(String(60), default="")
    counted: Mapped[bool] = mapped_column(Boolean, default=False)  # counts towards earned income
    matched_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_status: Mapped[str] = mapped_column(String(20), default="")  # matched | unmatched_payout | bank_only | ""
    flags: Mapped[list] = mapped_column(JSON, default=list)
    rule: Mapped[str] = mapped_column(String(60), default="")
    tagged_by: Mapped[str] = mapped_column(String(20), default="rules")  # rules | llm | user
    balance: Mapped[float | None] = mapped_column(Float, nullable=True)
    active_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_ledger_user_date", "user_id", "date"),)


class WeeklySeries(Base):
    __tablename__ = "weekly_series"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week: Mapped[date] = mapped_column(Date)
    earned: Mapped[float] = mapped_column(Float, default=0.0)
    active_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_mix: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("user_id", "week"),)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(20), unique=True)
    kind: Mapped[str] = mapped_column(String(20))  # scorecard | ebm
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    features: Mapped[list] = mapped_column(JSON, default=list)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    training_data: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    artifact_path: Mapped[str] = mapped_column(String(400), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    as_of: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(20), default="on_demand")  # on_demand | monthly | refresh
    model_version: Mapped[str] = mapped_column(String(20))
    input_hash: Mapped[str] = mapped_column(String(64))
    score: Mapped[int] = mapped_column(Integer)
    band: Mapped[str] = mapped_column(String(1))
    confidence: Mapped[str] = mapped_column(String(10))
    dsi: Mapped[float] = mapped_column(Float)
    dsi_parts: Mapped[dict] = mapped_column(JSON, default=dict)
    safe_emi: Mapped[float] = mapped_column(Float)
    alpha: Mapped[float] = mapped_column(Float)
    f20: Mapped[float] = mapped_column(Float)
    e_ess: Mapped[float] = mapped_column(Float)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    watchouts: Mapped[list] = mapped_column(JSON, default=list)
    seasonality_method: Mapped[str] = mapped_column(String(30))
    series: Mapped[dict] = mapped_column(JSON, default=dict)
    reconciliation: Mapped[dict] = mapped_column(JSON, default=dict)
    pillars: Mapped[list[PillarScore]] = relationship(cascade="all, delete-orphan", order_by="PillarScore.id")
    reasons: Mapped[list[ReasonCode]] = relationship(cascade="all, delete-orphan", order_by="ReasonCode.id")


class PillarScore(Base):
    __tablename__ = "pillar_scores"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True)
    pillar: Mapped[str] = mapped_column(String(20))
    score: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)
    contribution: Mapped[float] = mapped_column(Float)
    components: Mapped[dict] = mapped_column(JSON, default=dict)


class ReasonCode(Base):
    __tablename__ = "reason_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    pillar: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))  # positive | negative
    impact: Mapped[float] = mapped_column(Float, default=0.0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)


class ShareLink(Base):
    __tablename__ = "share_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey("lenders.id"))
    token: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lender: Mapped[Lender] = relationship()

    def is_valid(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return self.revoked_at is None and self.expires_at > now


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lender_id: Mapped[int] = mapped_column(ForeignKey("lenders.id"), index=True)
    share_link_id: Mapped[int] = mapped_column(ForeignKey("share_links.id"))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    requested_amount: Mapped[float] = mapped_column(Float)
    requested_tenure_weeks: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(30))  # submitted | manual_review_required | approved | modified | declined
    routing_reasons: Mapped[list] = mapped_column(JSON, default=list)
    suggested_outcome: Mapped[str] = mapped_column(String(20))  # approve | review
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user: Mapped[User] = relationship()
    lender: Mapped[Lender] = relationship()
    share_link: Mapped[ShareLink] = relationship()
    snapshot: Mapped[Snapshot] = relationship()
    decisions: Mapped[list[Decision]] = relationship(order_by="Decision.id", back_populates="application")


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    officer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    outcome: Mapped[str] = mapped_column(String(10))  # approve | modify | decline
    reason_code: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)
    weekly_emi: Mapped[float | None] = mapped_column(Float, nullable=True)
    tenure_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    payout_day: Mapped[str] = mapped_column(String(10), default="")
    skip_weeks: Mapped[list] = mapped_column(JSON, default=list)
    agrees_with_suggestion: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    application: Mapped[Application] = relationship(back_populates="decisions")
    officer: Mapped[User] = relationship()


class Override(Base):
    __tablename__ = "overrides"
    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decisions.id", ondelete="CASCADE"))
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    officer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    suggested: Mapped[str] = mapped_column(String(20))
    chosen: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str] = mapped_column(String(40))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Dispute(Base):
    __tablename__ = "disputes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id"), nullable=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("snapshots.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(30))  # score | decision | data
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | in_review | resolved
    response: Mapped[str] = mapped_column(Text, default="")
    responder_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class EarlyWarning(Base):
    __tablename__ = "early_warnings"
    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    prev_snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    new_snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id"))
    f20_prev: Mapped[float] = mapped_column(Float)
    f20_new: Mapped[float] = mapped_column(Float)
    drop_pct: Mapped[float] = mapped_column(Float)
    suggestion: Mapped[str] = mapped_column(String(30))  # skip_week | restructure
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(40), default="")
    target_id: Mapped[str] = mapped_column(String(40), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str] = mapped_column(String(64), default="")


class CohortSeasonality(Base):
    __tablename__ = "cohort_seasonality"
    id: Mapped[int] = mapped_column(primary_key=True)
    city: Mapped[str] = mapped_column(String(60))
    work_type: Mapped[str] = mapped_column(String(30))
    week_of_year: Mapped[int] = mapped_column(Integer)
    index: Mapped[float] = mapped_column(Float)
    n_workers: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("city", "work_type", "week_of_year"),)


class SimRun(Base):
    __tablename__ = "sim_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    fairness: Mapped[dict] = mapped_column(JSON, default=dict)
    calibration: Mapped[list] = mapped_column(JSON, default=list)
    recourse: Mapped[dict] = mapped_column(JSON, default=dict)
    model_comparison: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0)
