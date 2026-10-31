"""Model versions: v1 expert scorecard (always available) and v2 EBM trained on simulator outcomes."""
from __future__ import annotations

import pickle
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ModelVersion
from app.scoring import config as C
from app.scoring.engine import band_for

PILLARS = list(C.PILLAR_WEIGHTS)


def ensure_v1(db: Session) -> ModelVersion:
    mv = db.scalar(select(ModelVersion).where(ModelVersion.version == C.MODEL_VERSION_V1))
    if mv:
        return mv
    mv = ModelVersion(
        version=C.MODEL_VERSION_V1, kind="scorecard", is_active=True, validated=True,
        features=[{"pillar": p, "components": list(C.SUB_WEIGHTS[p])} for p in PILLARS],
        weights={"pillars": C.PILLAR_WEIGHTS, "components": C.SUB_WEIGHTS, "curves": {k: v for k, v in C.CURVES.items()},
                 "bands": C.BANDS},
        training_data={"description": "Expert scorecard: weights set by design, not fitted to data."},
        notes="Glass-box weighted sum of five income-neutral pillars. Income level, hours worked and protected "
              "attributes are not inputs.",
    )
    if not db.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True))):
        mv.is_active = True
    db.add(mv)
    db.flush()
    return mv


def active(db: Session) -> ModelVersion:
    mv = db.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True)))
    return mv or ensure_v1(db)


@lru_cache(maxsize=4)
def _load(path: str):
    with open(path, "rb") as fh:
        return pickle.load(fh)


def score(mv: ModelVersion, run_out: dict) -> tuple[int, str]:
    """Score with the given model version. v1 uses the scorecard; an EBM maps pillar scores to P(no default)."""
    if mv.kind == "ebm" and mv.artifact_path and Path(mv.artifact_path).exists():
        model = _load(mv.artifact_path)
        x = [[run_out["pillars"][p]["score"] for p in PILLARS]]
        p_ok = float(model.predict_proba(x)[0][1])
        s = int(round(100 * p_ok))
        return s, band_for(s)
    return run_out["score"], run_out["band"]


def activate(db: Session, version: str) -> ModelVersion:
    target = db.scalar(select(ModelVersion).where(ModelVersion.version == version))
    if not target:
        raise ValueError("Unknown model version")
    for mv in db.scalars(select(ModelVersion)).all():
        mv.is_active = mv.id == target.id
    db.flush()
    return target
