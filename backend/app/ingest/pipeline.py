"""Ingestion pipeline: upload -> raw file -> parse -> transactions -> reconciled ledger -> weekly series.

The seeded generator calls exactly these functions (no side door into the database).
"""
from __future__ import annotations

import hashlib
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingest import parsers
from app.ingest.classify import classify, payer_of
from app.ingest.reconcile import Credit, Movement, Payout, find_round_trips, reconcile
from app.models import Consent, LedgerEntry, RawFile, Source, Transaction, User, WeeklySeries

LARGE_CREDIT_MULTIPLE = 3.0
ROUND_TRIP_MIN_AMOUNT = 500.0


class IngestError(Exception):
    pass


def week_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _row_hash(user_id: int, kind: str, r: parsers.ParsedRow, occurrence: int) -> str:
    key = f"{user_id}|{kind}|{r.date.isoformat()}|{r.direction}|{r.amount:.2f}|{r.narration.strip().upper()}|" \
          f"{'' if r.balance is None else f'{r.balance:.2f}'}|{r.ref.strip().upper()}|{r.platform}|{occurrence}"
    return hashlib.sha256(key.encode()).hexdigest()


def store_upload(db: Session, user: User, consent: Consent, kind: str, filename: str, data: bytes,
                 label: str = "", institution: str = "", account_ref: str = "", platform: str = "",
                 rebuild: bool = True) -> Source:
    s = get_settings()
    if kind not in {"bank_statement", "platform_statement"}:
        raise IngestError("Choose whether this is a bank statement or a platform payout statement.")
    if not consent or consent.user_id != user.id or not consent.is_active() or consent.source_kind != kind:
        raise IngestError("An active consent for this type of source is required before uploading.")
    if len(data) == 0:
        raise IngestError("The file is empty.")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise IngestError(f"The file is larger than {s.max_upload_mb} MB.")
    try:
        ftype = parsers.sniff_type(filename, data)
    except parsers.ParseError as e:
        raise IngestError(str(e)) from e
    if kind == "platform_statement" and ftype == "xlsx":
        pass  # allowed: payout exports are sometimes Excel
    folder = s.upload_dir / str(user.id)
    folder.mkdir(parents=True, exist_ok=True)
    stored = folder / f"{uuid.uuid4().hex}.{ftype}"
    stored.write_bytes(data)
    tail = "".join(ch for ch in account_ref if ch.isdigit())[-4:]
    source = Source(user_id=user.id, consent_id=consent.id, kind=kind,
                    label=(label or Path(filename).stem)[:120], institution=(institution or platform)[:120],
                    account_ref=f"XXXX{tail}" if tail else "", status="pending")
    source.raw_files.append(RawFile(filename=Path(filename).name[:200], stored_path=stored.relative_to(s.upload_dir).as_posix(), size=len(data),
                                    sha256=hashlib.sha256(data).hexdigest(), file_type=ftype))
    db.add(source)
    db.flush()
    raw = source.raw_files[0]
    try:
        table = parsers.read_table(data, ftype)
    except parsers.ParseError as e:
        source.status = "failed"
        source.error = str(e)
        db.flush()
        return source
    if not table.rows:
        source.status = "failed"
        source.error = "No transaction rows were found in this file."
        db.flush()
        return source
    mapping, conf = parsers.detect_mapping(table, kind)
    if kind == "platform_statement" and platform and not mapping.get("platform"):
        mapping["default_platform"] = platform
    raw.detected_mapping = mapping
    raw.mapping_confidence = conf
    if conf >= parsers.MAPPING_CONFIDENCE_REQUIRED:
        process_source(db, source, mapping, table=table, rebuild=rebuild)
    else:
        source.status = "needs_mapping"
    db.flush()
    return source


def stored_file(raw: RawFile) -> Path:
    """Uploaded files live under UPLOAD_DIR (outside the web root); the DB keeps the relative path."""
    return get_settings().upload_dir / raw.stored_path


def load_table(source: Source) -> parsers.Table:
    raw = source.raw_files[0]
    return parsers.read_table(stored_file(raw).read_bytes(), raw.file_type)


def process_source(db: Session, source: Source, mapping: dict, table: parsers.Table | None = None,
                   rebuild: bool = True) -> Source:
    table = table or load_table(source)
    result = parsers.normalize(table, mapping, source.kind, default_platform=mapping.get("default_platform", ""))
    raw = source.raw_files[0]
    raw.detected_mapping = mapping
    existing = set(db.scalars(select(Transaction.row_hash).join(Source, Source.id == Transaction.source_id)
                              .where(Transaction.user_id == source.user_id, Source.kind == source.kind,
                                     Source.status != "revoked")).all())
    seen: Counter = Counter()
    added = dup = 0
    rows = []
    for r in result.rows:
        base = (r.date, r.direction, r.amount, r.narration.strip().upper(), r.balance, r.ref.strip().upper(), r.platform)
        occ = seen[base]
        seen[base] += 1
        h = _row_hash(source.user_id, source.kind, r, occ)
        if h in existing:
            dup += 1
            continue
        existing.add(h)
        rows.append(Transaction(source_id=source.id, user_id=source.user_id, date=r.date, narration=r.narration,
                                direction=r.direction, amount=r.amount, balance=r.balance, ref=r.ref, platform=r.platform,
                                trips=r.trips, active_hours=r.active_hours, row_number=r.row_number, row_hash=h))
        added += 1
    db.add_all(rows)
    source.parsed_count = added
    source.duplicate_count = dup
    source.skipped_count = len(result.skipped)
    source.skipped_rows = result.skipped[:200]
    if added == 0 and dup == 0:
        source.status = "failed"
        source.error = "No transactions could be read from this file. Check the column mapping or upload a CSV."
    else:
        source.status = "processed"
        source.error = ""
    db.flush()
    if rebuild:
        rebuild_ledger(db, source.user_id)
    return source


def rebuild_ledger(db: Session, user_id: int) -> None:
    """Classify, detect round trips, reconcile payouts with bank credits and rebuild the weekly series.

    Ledger rows are updated in place (one per transaction) so evidence links in stored snapshots stay valid.
    """
    user = db.get(User, user_id)
    sources = db.scalars(select(Source).where(Source.user_id == user_id, Source.status == "processed")).all()
    src_by_id = {s.id: s for s in sources}
    own_refs = [s.account_ref for s in sources if s.kind == "bank_statement" and s.account_ref]
    txns = db.scalars(select(Transaction).where(Transaction.source_id.in_(src_by_id.keys())).order_by(Transaction.date, Transaction.id)).all() if src_by_id else []
    existing = {le.transaction_id: le for le in db.scalars(select(LedgerEntry).where(LedgerEntry.user_id == user_id)).all()}
    keep = {t.id for t in txns}
    stale = [le.id for tid, le in existing.items() if tid not in keep]
    if stale:
        db.execute(delete(LedgerEntry).where(LedgerEntry.id.in_(stale)))

    entries: dict[int, LedgerEntry] = {}
    for t in txns:
        le = existing.get(t.id)
        if le is None:
            le = LedgerEntry(user_id=user_id, transaction_id=t.id, source_id=t.source_id)
            db.add(le)
        src = src_by_id[t.source_id]
        le.source_kind = src.kind
        le.date, le.week, le.direction, le.amount = t.date, week_of(t.date), t.direction, t.amount
        le.narration, le.balance, le.active_hours = t.narration, t.balance, t.active_hours
        le.flags, le.matched_to, le.match_status = [], None, ""
        if src.kind == "platform_statement":
            le.kind = "earned" if t.direction == "credit" else "expense"
            le.category = "payout_statement" if t.direction == "credit" else "platform_deduction"
            le.platform = t.platform or src.institution
            le.counted = False
            le.rule = "platform_statement"
            le.tagged_by = "rules"
        elif le.tagged_by == "user":
            le.counted = le.kind == "earned"
        else:
            tag = classify(t.narration, t.direction, own_refs, user.name if user else "")
            le.kind, le.category, le.platform, le.rule, le.tagged_by = tag.kind, tag.category, tag.platform, tag.rule, "rules"
            le.counted = tag.kind == "earned"
        entries[t.id] = le

    bank = [(t, entries[t.id]) for t in txns if src_by_id[t.source_id].kind == "bank_statement"]
    # Hidden own-account transfers: a credit mirroring an equal debit from another own account.
    moves = [Movement(t.id, t.source_id, t.date, t.amount, t.direction) for t, le in bank
             if t.amount >= ROUND_TRIP_MIN_AMOUNT and (
                 (t.direction == "debit" and le.category in {"self_transfer", "general"}) or
                 (t.direction == "credit" and le.kind in {"earned", "other", "self_transfer"} and le.category != "payout"))]
    for tid in find_round_trips(moves):
        le = entries[tid]
        hidden = le.kind != "self_transfer"
        le.kind, le.category, le.counted = "self_transfer", "self_transfer", False
        if hidden:
            le.flags = sorted(set(le.flags) | {"round_trip"})
            le.rule = "round_trip_detected"

    payouts = [Payout(t.id, t.date, t.amount, entries[t.id].platform) for t in txns
               if src_by_id[t.source_id].kind == "platform_statement" and t.direction == "credit"]
    credits = [Credit(t.id, t.date, t.amount, t.narration, le.platform) for t, le in bank
               if t.direction == "credit" and le.kind == "earned"]
    matches, unmatched = reconcile(payouts, credits)
    db.flush()  # assign ids to new ledger rows so pairs can reference each other
    for pid, cid in matches:
        p, c = entries[pid], entries[cid]
        p.match_status = c.match_status = "matched"
        p.platform = p.platform or c.platform
        c.platform = c.platform or p.platform
        c.category = "payout"
        c.counted, p.counted = True, False
        p.matched_to, c.matched_to = c.id, p.id
    for pid in unmatched:
        p = entries[pid]
        p.match_status = "unmatched_payout"
        p.flags = sorted(set(p.flags) | {"unmatched_payout"})
    for t, le in bank:
        if le.kind == "earned" and le.match_status == "":
            le.match_status = "bank_only"

    # Unexplained large credits: non-platform credits above 3x the median weekly earned income are not counted.
    weekly = defaultdict(float)
    for t, le in bank:
        if le.counted:
            weekly[le.week] += le.amount
    med = statistics.median(v for v in weekly.values() if v > 0) if any(v > 0 for v in weekly.values()) else 0.0
    if med > 0:
        for t, le in bank:
            if le.direction == "credit" and le.kind in {"earned", "other"} and le.category not in {"payout", "interest"} \
                    and le.amount > LARGE_CREDIT_MULTIPLE * med and le.match_status != "matched":
                le.counted = False
                le.flags = sorted(set(le.flags) | {"unexplained_large_credit"})
    db.flush()
    rebuild_weekly(db, user_id, list(entries.values()), src_by_id)


def rebuild_weekly(db: Session, user_id: int, entries: list[LedgerEntry], src_by_id: dict[int, Source]) -> None:
    db.execute(delete(WeeklySeries).where(WeeklySeries.user_id == user_id))
    if not entries:
        db.flush()
        return
    first = week_of(min(e.date for e in entries))
    last = week_of(max(e.date for e in entries))
    earned: dict[date, float] = defaultdict(float)
    hours: dict[date, float] = defaultdict(float)
    has_hours: set[date] = set()
    mix: dict[date, dict] = defaultdict(lambda: defaultdict(float))
    for e in entries:
        if e.counted:
            earned[e.week] += e.amount
            key = e.platform or (payer_of(e.narration) if e.category == "client_payment_fx" else src_by_id[e.source_id].label)
            if e.category == "customer_payment":
                key = "Direct customer payments"
            mix[e.week][key] += e.amount
        if e.source_kind == "platform_statement" and e.active_hours is not None:
            hours[e.week] += e.active_hours
            has_hours.add(e.week)
    rows = []
    w = first
    while w <= last:
        rows.append(WeeklySeries(user_id=user_id, week=w, earned=round(earned.get(w, 0.0), 2),
                                 active_hours=round(hours[w], 2) if w in has_hours else None,
                                 source_mix={k: round(v, 2) for k, v in mix.get(w, {}).items()}))
        w += timedelta(days=7)
    db.add_all(rows)
    db.flush()


def delete_source(db: Session, source: Source) -> None:
    """Remove a source, its raw file on disk and every row derived from it, then rebuild the ledger."""
    for raw in source.raw_files:
        stored_file(raw).unlink(missing_ok=True)
    user_id = source.user_id
    db.execute(delete(LedgerEntry).where(LedgerEntry.source_id == source.id))
    db.execute(delete(Transaction).where(Transaction.source_id == source.id))
    db.delete(source)
    db.flush()
    rebuild_ledger(db, user_id)
