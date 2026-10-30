"""Actionable recourse (BUILD.md 6.7): constrained search over actionable features only.

Each candidate is re-scored with the real scoring function (engine.score_features). Only candidates that
move the worker into a better band are returned. Hours worked, number of platforms and income level are
locked and never changed.
"""
from __future__ import annotations

import itertools

from app.scoring import config as C
from app.scoring.engine import band_for, score_features

BAND_RANK = {b: i for i, (b, _) in enumerate(C.BANDS)}  # A=0 ... E=4

# effort: rough cost of each change, to prefer the easiest steps
_EFFORT = {"bounces": 1.0, "on_time_rate": 1.5, "buffer_days": 2.0, "active_week_share": 3.0}


def _candidates(f: dict) -> list[tuple[str, float]]:
    out = []
    for feat, values in C.RECOURSE_ACTIONABLE.items():
        cur = f.get(feat)
        for v in values:
            if feat == "active_week_share":
                target = min(1.0, (cur or 0.0) + v)
                if target <= (cur or 0.0):
                    continue
            elif feat == "bounces":
                target = float(v)
                if cur is None or cur <= target:
                    continue
            else:
                target = float(v)
                if cur is not None and cur >= target:
                    continue
            out.append((feat, round(target, 4)))
    return out


def _apply(f: dict, changes: tuple[tuple[str, float], ...]) -> dict:
    g = dict(f)
    for feat, v in changes:
        g[feat] = v
    return g


def search(features: dict) -> dict:
    base = score_features(features)
    cands = _candidates(features)
    found = []
    for r in (1, 2):
        for combo in itertools.combinations(cands, r):
            if len({c[0] for c in combo}) < r:
                continue
            res = score_features(_apply(features, combo))
            if BAND_RANK[res["band"]] < BAND_RANK[base["band"]]:
                effort = sum(_EFFORT[c[0]] * (1 + abs((c[1] or 0) - (features.get(c[0]) or 0)) / 10) for c in combo)
                found.append({"changes": [{"feature": c[0], "from": features.get(c[0]), "to": c[1]} for c in combo],
                              "new_score": res["score"], "new_band": res["band"], "effort": round(effort, 3)})
        if len(found) >= C.RECOURSE_MAX_STEPS:
            break
    # One step per feature: prefer the easiest single change for each feature; use a pair only when
    # neither of its features already has a single step, and never reuse a feature across steps.
    found.sort(key=lambda s: (len(s["changes"]), s["effort"], -s["new_score"]))
    chosen, used = [], set()
    for s in found:
        feats = {c["feature"] for c in s["changes"]}
        if feats & used:
            continue
        chosen.append(s)
        used |= feats
    chosen = sorted(chosen, key=lambda s: s["effort"])[: C.RECOURSE_MAX_STEPS]
    return {"current_score": base["score"], "current_band": base["band"], "steps": chosen,
            "locked": C.RECOURSE_LOCKED, "top_band": base["band"] == C.BANDS[0][0],
            "feasible": bool(chosen)}


def verify_step(features: dict, step: dict) -> bool:
    """Re-score a step independently; used by tests and before showing a step."""
    g = _apply(features, tuple((c["feature"], c["to"]) for c in step["changes"]))
    return band_for(score_features(g)["score"]) == step["new_band"]
