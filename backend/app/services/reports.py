"""Serialise snapshots into the worker passport and the evidence-linked lender report."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LedgerEntry, ReasonCode, Snapshot, Source, User
from app.scoring import config as C
from app.scoring import recourse
from app.services import language
from app.services.snapshots import active_sources

PILLAR_ORDER = list(C.PILLAR_WEIGHTS)


def pillars_out(snap: Snapshot) -> list[dict]:
    by = {p.pillar: p for p in snap.pillars}
    return [{"pillar": p, "score": round(by[p].score), "weight": by[p].weight, "contribution": round(by[p].contribution, 1),
             "components": by[p].components} for p in PILLAR_ORDER if p in by]


def reasons_out(snap: Snapshot, lang: str, limit: int | None = None) -> list[dict]:
    rs = sorted(snap.reasons, key=lambda r: -abs(r.impact))
    out = []
    for r in rs[:limit] if limit else rs:
        ex = language.explain(r.code, r.params, lang)
        out.append({"id": r.id, "code": r.code, "pillar": r.pillar, "direction": r.direction, "impact": r.impact,
                    "text": ex["text"], "text_source": ex["source"], "evidence_count": len(r.evidence_ids),
                    "sub": r.params.get("sub")})
    return out


def watchouts_out(snap: Snapshot, lang: str) -> list[dict]:
    return [{"code": w["code"], **language.explain(w["code"], w["params"], lang)} for w in snap.watchouts]


def trend(db: Session, user_id: int, current: Snapshot) -> list[dict]:
    rows = db.scalars(select(Snapshot).where(Snapshot.user_id == user_id, Snapshot.kind == "monthly",
                                             Snapshot.model_version == current.model_version,
                                             Snapshot.as_of < current.as_of).order_by(Snapshot.as_of)).all()
    seen, out = set(), []
    for s in list(rows) + [current]:
        if s.as_of in seen:
            continue
        seen.add(s.as_of)
        out.append({"as_of": s.as_of.isoformat(), "score": s.score, "band": s.band, "confidence": s.confidence,
                    "f20": s.f20, "safe_emi": s.safe_emi})
    return out


def sources_summary(db: Session, user_id: int) -> list[dict]:
    return [{"id": s.id, "kind": s.kind, "label": s.label, "institution": s.institution, "account_ref": s.account_ref,
             "parsed": s.parsed_count} for s in active_sources(db, user_id)]


def passport_out(db: Session, user: User, snap: Snapshot, lang: str = "en", with_recourse: bool = False) -> dict:
    f = snap.features
    out = {
        "snapshot_id": snap.id, "as_of": snap.as_of.isoformat(), "created_at": snap.created_at.isoformat(),
        "model_version": snap.model_version, "input_hash": snap.input_hash,
        "score": snap.score, "band": snap.band, "confidence": snap.confidence, "show_band": snap.confidence != "Low",
        "dsi": snap.dsi_parts, "safe_emi": snap.safe_emi, "alpha": snap.alpha, "f20": snap.f20, "e_ess": snap.e_ess,
        "e_ess_parts": f.get("e_ess_parts", {}), "capacity_warning": snap.f20 <= snap.e_ess,
        "pillars": pillars_out(snap), "reasons": reasons_out(snap, lang), "watchouts": watchouts_out(snap, lang),
        "series": snap.series, "seasonality_method": snap.seasonality_method,
        "volatility": {"raw": round(f.get("v_raw", 0), 4), "unexplained": round(f.get("v_res", 0), 4)},
        "features": {k: f.get(k) for k in ("active_week_share", "longest_gap_days", "buffer_days", "on_time_rate",
                                             "bounces", "savings_rate", "avg_hours", "weeks_over_60", "months",
                                             "n_sources", "reconcile_rate", "median_week", "mean_week", "platform_count")},
        "reconciliation": snap.reconciliation, "trend": trend(db, user.id, snap), "flags": snap.flags,
        "sources": sources_summary(db, user.id),
    }
    if snap.confidence == "Low":
        out["sufficiency_message"] = language.sufficiency_message(f, snap.dsi_parts, lang)
    if with_recourse:
        out["recourse"] = recourse_out(snap, lang)
    return out


def recourse_out(snap: Snapshot, lang: str) -> dict:
    res = recourse.search(snap.features)
    steps = []
    for s in res["steps"]:
        if not recourse.verify_step(snap.features, s):
            continue
        steps.append({**s, "text": language.recourse_text(s, res["current_band"], lang)})
    return {"current_band": res["current_band"], "current_score": res["current_score"], "steps": steps,
            "top_band": res["top_band"], "locked": res["locked"]}


def evidence_rows(db: Session, user_id: int, ids: list[int], limit: int = 400) -> list[dict]:
    if not ids:
        return []
    rows = db.execute(select(LedgerEntry, Source.label).join(Source, Source.id == LedgerEntry.source_id)
                      .where(LedgerEntry.id.in_(ids[:limit]), LedgerEntry.user_id == user_id)
                      .order_by(LedgerEntry.date.desc(), LedgerEntry.id)).all()
    return [ledger_row(le, label) for le, label in rows]


def ledger_row(le: LedgerEntry, source_label: str = "") -> dict:
    return {"id": le.id, "date": le.date.isoformat(), "narration": le.narration, "direction": le.direction,
            "amount": le.amount, "kind": le.kind, "category": le.category, "platform": le.platform,
            "counted": le.counted, "match_status": le.match_status, "matched_to": le.matched_to, "flags": le.flags,
            "rule": le.rule, "tagged_by": le.tagged_by, "balance": le.balance, "active_hours": le.active_hours,
            "source": source_label, "source_kind": le.source_kind}


def reason_evidence(db: Session, snap: Snapshot, reason_id: int) -> dict:
    r = db.get(ReasonCode, reason_id)
    if not r or r.snapshot_id != snap.id:
        return {}
    return {"reason": {"id": r.id, "code": r.code, "pillar": r.pillar,
                       "text": language.explain(r.code, r.params, "en")["text"]},
            "rows": evidence_rows(db, snap.user_id, r.evidence_ids)}


def pillar_evidence(db: Session, snap: Snapshot, pillar: str) -> dict:
    ids: list[int] = []
    for r in snap.reasons:
        if r.pillar == pillar:
            ids.extend(i for i in r.evidence_ids if i not in ids)
    return {"pillar": pillar, "rows": evidence_rows(db, snap.user_id, ids)}
