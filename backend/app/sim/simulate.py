"""Validation simulator (BUILD.md section 7).

Simulates >= 5,000 workers. Each worker's history (26-78 weeks) is scored with the real scoring engine;
the life then continues for 26 more weeks with a new weekly loan EMI. A worker defaults ONLY when cash
cannot cover the EMI for three consecutive payout cycles (sim/life.py). Default is never derived from
scoring features. EarnScore is compared with a bureau-style baseline. Results are stored in sim_runs.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import pickle
import time
from collections import defaultdict
from datetime import timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingest.reconcile import Credit, Payout, reconcile
from app.models import ModelVersion, SimRun
from app.scoring import config as C
from app.scoring import engine, recourse
from app.services import model_registry
from app.services.snapshots import cohort_for
from app.sim.life import CITIES, EFFECTS, END_DATE, WORK_TYPES, Life, live, make_persona

log = logging.getLogger("earnscore.simulate")
SIM_SEED = 7_2026
OUTCOME_WEEKS = 26
HISTORY_WEEKS = (26, 79)
EMI_SHARE = (0.08, 0.35)          # requested weekly EMI as a share of the worker's typical weekly income
BUREAU_FILE_PROB = {"existing_loan": 0.7, "none": 0.15}
BUREAU_THRESHOLD = 650
BAND_APPROVE = {"A", "B", "C"}


def to_input(life: Life, cohort_index, cohort_n) -> engine.ScoringInput:
    """Scoring input from the simulated ledger (ground-truth categories; payouts reconciled with the real rule)."""
    E = engine.Event
    hist = [t for t in life.txns if t.date <= END_DATE]
    ids = iter(range(1, 10_000_000))
    weeks, earned, hours = [], [], []
    w = life.start
    while w <= END_DATE:
        weeks.append(w)
        earned.append(0.0)
        hours.append(life.weekly_hours.get(w) if life.persona.platforms else None)
        w += timedelta(days=7)
    widx = {w: i for i, w in enumerate(weeks)}
    inp = engine.ScoringInput(as_of=END_DATE, weeks=weeks, earned=earned, hours=hours, first_date=hist[0].date if hist else None,
                              n_sources=life.persona.accounts + (len(life.persona.platforms) if life.persona.platforms else 0),
                              cohort_index=cohort_index, cohort_n=cohort_n)
    credits = []
    for t in hist:
        i = next(ids)
        wk = t.date - timedelta(days=t.date.weekday())
        if t.direction == "credit" and t.category == "earned":
            key = t.platform or ("Direct customer payments" if "UPI/CR" in t.narration else t.narration.split("-")[-1][:20])
            inp.income.append(E(i, t.date, t.amount, key=key))
            if wk in widx:
                earned[widx[wk]] += t.amount
            if t.platform:
                credits.append(Credit(i, t.date, t.amount, t.narration, t.platform))
        if t.direction == "debit":
            if t.category in {"rent", "utilities", "fuel", "emi", "bounce", "spend"}:
                inp.spend.append(E(i, t.date, t.amount, category=t.category))
            if t.category in {"rent", "utilities", "fuel", "emi"}:
                inp.essentials.append(E(i, t.date, t.amount, category=t.category))
            if t.category in {"rent", "utilities", "emi"}:
                inp.bills.append(E(i, t.date, t.amount, key=t.narration[:14], category=t.category))
            if t.category == "bounce":
                inp.bounces.append(E(i, t.date, t.amount))
            if t.category == "savings":
                inp.savings.append(E(i, t.date, t.amount))
        inp.balances.append(E(i, t.date, t.amount, source_id=t.account, balance=t.balance))
    payouts = [Payout(next(ids), r.date, r.amount, r.platform) for r in life.payouts]
    matches, _ = reconcile(payouts, credits)
    matched = {m[0] for m in matches}
    for p, r in zip(payouts, life.payouts):
        inp.payouts.append(E(p.id, p.date, p.amount, key=p.platform, matched=p.id in matched, hours=r.hours))
    return inp


def _simulate_one(job) -> dict:
    """One simulated worker: history, score with the real engine, then 26 weeks of repayment."""
    i, seed, city, wt, hist, accts, (cidx, cn) = job
    rng = np.random.default_rng([seed, i])
    p = make_persona(rng, 50_000 + i, f"Sim {i}", city, wt, hist, accts)
    emi = round(p.base_weekly * float(rng.uniform(*EMI_SHARE)), 0)
    life = live(p, seed=seed + i, extra_weeks=OUTCOME_WEEKS, loan_emi=emi)
    out = engine.run(to_input(life, cidx, cn))
    # Bureau-style baseline: a file exists mostly for workers with an existing formal loan. The synthetic bureau
    # score reflects what a bureau observes - the repayment record on that loan (bounced EMIs) - plus noise.
    has_file = rng.random() < BUREAU_FILE_PROB["existing_loan" if p.has_emi else "none"]
    bounced = sum(1 for t in life.txns if t.date <= END_DATE and t.category == "bounce")
    if not has_file:
        bureau = None
    elif p.has_emi:
        bureau = float(np.clip(780 - 70 * bounced + rng.normal(0, 50), 300, 900))
    else:
        bureau = float(np.clip(650 + rng.normal(0, 80), 300, 900))
    return {"score": out["score"], "band": out["band"], "confidence": out["confidence"], "safe_emi": out["emi"]["safe_emi"],
            "emi": emi, "default": int(life.outcome["defaulted"]), "bureau": bureau, "group": p.group,
            "work_type": wt, "city": city, "weeks": hist,
            "pillars": [out["pillars"][k]["score"] for k in C.PILLAR_WEIGHTS], "features": out["features"]}


def _auc(y_good: np.ndarray, s: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y_good, s)) if 0 < y_good.sum() < len(y_good) else float("nan")


def _ks(y_good: np.ndarray, s: np.ndarray) -> float:
    order = np.argsort(s)
    g = np.cumsum(y_good[order]) / max(y_good.sum(), 1)
    b = np.cumsum(1 - y_good[order]) / max((1 - y_good).sum(), 1)
    return float(np.max(np.abs(g - b)))


def _approve_at_rate(s: np.ndarray, default: np.ndarray, max_rate: float) -> np.ndarray:
    """Largest top-score set whose default rate does not exceed max_rate."""
    order = np.argsort(-s, kind="stable")
    cum_def = np.cumsum(default[order])
    n = np.arange(1, len(s) + 1)
    ok = np.where(cum_def / n <= max_rate + 1e-12)[0]
    k = int(ok.max()) + 1 if len(ok) else 0
    approved = np.zeros(len(s), dtype=bool)
    approved[order[:k]] = True
    return approved


def _policy(approved: np.ndarray, default: np.ndarray) -> dict:
    good = default == 0
    return {"approval_rate": round(float(approved.mean()), 4),
            "default_rate_approved": round(float(default[approved].mean()), 4) if approved.any() else None,
            "creditworthy_rejected_share": round(float((~approved & good).sum() / max(good.sum(), 1)), 4)}


def _fairness(group: np.ndarray, approved: np.ndarray, good: np.ndarray) -> dict:
    from fairlearn.metrics import MetricFrame, false_negative_rate, selection_rate

    mf = MetricFrame(metrics={"selection_rate": selection_rate, "false_negative_rate": false_negative_rate},
                     y_true=good.astype(int), y_pred=approved.astype(int), sensitive_features=group)
    by = {g: {k: round(float(v), 4) for k, v in row.items()} for g, row in mf.by_group.to_dict(orient="index").items()}
    diff = {k: round(float(v), 4) for k, v in mf.difference().to_dict().items()}
    counts = {g: int((group == g).sum()) for g in np.unique(group)}
    return {"by_group": by, "difference": diff, "counts": counts}


def run(db: Session, n_workers: int = 5000, seed: int = SIM_SEED) -> SimRun:
    t0 = time.time()
    rng = np.random.default_rng(seed)
    model_registry.ensure_v1(db)
    cohorts = {(c, w): cohort_for(db, c, w) for c in CITIES for w in WORK_TYPES}
    jobs = []
    for i in range(n_workers):
        city = CITIES[int(rng.integers(len(CITIES)))]
        wt = WORK_TYPES[int(rng.integers(len(WORK_TYPES)))]
        hist = int(rng.integers(*HISTORY_WEEKS))
        accts = int(rng.choice([1, 2, 2, 3]))
        jobs.append((i, seed, city, wt, hist, accts, cohorts[(city, wt)]))
    procs = max(1, min(8, (os.cpu_count() or 2) - 1))
    if procs > 1 and n_workers >= 200:
        with mp.get_context("spawn" if os.name == "nt" else "fork").Pool(procs) as pool:
            rows = pool.map(_simulate_one, jobs, chunksize=25)
    else:
        rows = [_simulate_one(j) for j in jobs]
    s = np.array([r["score"] for r in rows], dtype=float)
    d = np.array([r["default"] for r in rows])
    good = d == 0
    grp = np.array([r["group"] for r in rows])
    has_b = np.array([r["bureau"] is not None for r in rows])
    bscore = np.array([r["bureau"] or 0 for r in rows])
    base_approved = has_b & (bscore >= BUREAU_THRESHOLD)
    base = _policy(base_approved, d)
    eq_rate = base["default_rate_approved"] if base["default_rate_approved"] is not None else float(d.mean())
    es_equal = _approve_at_rate(s, d, eq_rate)
    bands = np.array([r["band"] for r in rows])
    conf = np.array([r["confidence"] for r in rows])
    es_band = np.isin(bands, list(BAND_APPROVE))
    calib = []
    for b, _ in C.BANDS:
        m = bands == b
        calib.append({"band": b, "n": int(m.sum()), "default_rate": round(float(d[m].mean()), 4) if m.any() else None,
                      "avg_score": round(float(s[m].mean()), 1) if m.any() else None})
    by_conf = {c: {"n": int((conf == c).sum()), "default_rate": round(float(d[conf == c].mean()), 4) if (conf == c).any() else None}
               for c in ("High", "Medium", "Low")}
    thin = ~has_b
    metrics = {
        "n_workers": n_workers, "default_rate": round(float(d.mean()), 4),
        "auc_earnscore": round(_auc(good.astype(int), s), 4), "ks_earnscore": round(_ks(good.astype(int), s), 4),
        "auc_bureau_on_file": round(_auc(good[has_b].astype(int), bscore[has_b]), 4) if has_b.any() else None,
        "bureau_file_share": round(float(has_b.mean()), 4),
        "baseline": base,
        "earnscore_equal_default_rate": _policy(es_equal, d) | {"target_default_rate": round(eq_rate, 4)},
        "earnscore_band_a_to_c": _policy(es_band, d),
        "approval_uplift_at_equal_default": round(_policy(es_equal, d)["approval_rate"] / base["approval_rate"], 3) if base["approval_rate"] else None,
        "thin_file": {"share": round(float(thin.mean()), 4),
                      "earnscore_approval_rate": round(float(es_equal[thin].mean()), 4) if thin.any() else None,
                      "default_rate": round(float(d[thin].mean()), 4) if thin.any() else None},
        "by_confidence": by_conf,
        "by_work_type": {wt: {"n": int(sum(1 for r in rows if r["work_type"] == wt)),
                              "avg_score": round(float(np.mean([r["score"] for r in rows if r["work_type"] == wt])), 1),
                              "default_rate": round(float(np.mean([r["default"] for r in rows if r["work_type"] == wt])), 4)}
                         for wt in WORK_TYPES},
    }
    fairness = {"earnscore_equal_default_rate": _fairness(grp, es_equal, good), "baseline": _fairness(grp, base_approved, good)}
    X = np.array([r["pillars"] for r in rows])
    gnum = (grp == "woman").astype(float)
    fairness["proxy_check"] = {k: round(float(abs(np.corrcoef(X[:, j], gnum)[0, 1])), 4) for j, k in enumerate(C.PILLAR_WEIGHTS)}
    fairness["proxy_note"] = "Absolute correlation between each pillar and the group attribute. The group attribute is never a model input."

    # recourse feasibility for Band C-E (constrained search, re-scored with the real function)
    rec_idx = [i for i, r in enumerate(rows) if r["band"] in {"C", "D", "E"}]
    sample = rec_idx[:600]
    feas = [recourse.search(rows[i]["features"])["feasible"] for i in sample]
    rec = {"band_c_to_e": len(rec_idx), "evaluated": len(sample),
           "feasible_rate": round(float(np.mean(feas)), 4) if feas else None,
           "by_band": {b: round(float(np.mean([f for i, f in zip(sample, feas) if rows[i]["band"] == b])), 4)
                       for b in ("C", "D", "E") if any(rows[i]["band"] == b for i in sample)}}

    comparison = _train_ebm(db, X, good.astype(int), s, d, eq_rate, seed)
    params = {
        "seed": seed, "n_workers": n_workers, "history_weeks": list(HISTORY_WEEKS), "outcome_weeks": OUTCOME_WEEKS,
        "total_weeks_range": [HISTORY_WEEKS[0] + OUTCOME_WEEKS, HISTORY_WEEKS[1] - 1 + OUTCOME_WEEKS],
        "personas": WORK_TYPES, "cities": CITIES, "seasonality_effects": EFFECTS,
        "shocks": {"deactivation": "Poisson rate 0.15/yr x (1.4 - reliability), 2-4 weeks",
                   "illness": "Poisson rate 0.3/yr x (1.4 - reliability), 1-3 weeks at 30% income",
                   "vehicle_breakdown": "Poisson rate 0.35/yr x (1.4 - reliability), repair cost Rs 2,500-9,000, 1 week at 50% income"},
        "loan": f"weekly EMI = {EMI_SHARE[0]:.0%}-{EMI_SHARE[1]:.0%} of the worker's typical weekly income, for {OUTCOME_WEEKS} weeks",
        "default_rule": "default only when total cash cannot cover the weekly EMI for 3 consecutive payout cycles",
        "bureau_baseline": f"a bureau file exists with probability {BUREAU_FILE_PROB['existing_loan']} for workers with an existing loan, "
                           f"{BUREAU_FILE_PROB['none']} otherwise; the synthetic bureau score (300-900) is 780 - 70 x bounced EMIs on "
                           f"the existing loan + noise (sd 50), or 650 + noise (sd 80) for files without a loan; "
                           f"approve if score >= {BUREAU_THRESHOLD}; thin-file workers are rejected",
        "earnscore_policy": "approve the highest scores while the approved default rate stays at or below the baseline's",
        "scoring": "scored with the v1 scorecard engine used by the app; classification uses the simulator's ground truth; "
                   "platform payouts are reconciled with the app's reconciliation rule",
    }
    run_row = SimRun(params=params, metrics=metrics, fairness=fairness, calibration=calib, recourse=rec,
                     model_comparison=comparison, duration_s=round(time.time() - t0, 1))
    db.add(run_row)
    db.commit()
    return run_row


def _train_ebm(db: Session, X: np.ndarray, y_good: np.ndarray, s_v1: np.ndarray, default: np.ndarray, eq_rate: float, seed: int) -> dict:
    from interpret.glassbox import ExplainableBoostingClassifier
    from sklearn.model_selection import train_test_split

    idx = np.arange(len(y_good))
    tr, te = train_test_split(idx, test_size=0.3, random_state=seed, stratify=y_good if 0 < y_good.sum() < len(y_good) else None)
    ebm = ExplainableBoostingClassifier(feature_names=list(C.PILLAR_WEIGHTS), monotone_constraints=[1] * X.shape[1],
                                        interactions=0, random_state=seed)
    ebm.fit(X[tr], y_good[tr])
    p = ebm.predict_proba(X[te])[:, 1]
    s_v2 = np.round(100 * p)
    auc_v1, auc_v2 = _auc(y_good[te], s_v1[te]), _auc(y_good[te], s_v2)
    appr_v1 = _approve_at_rate(s_v1[te], default[te], eq_rate)
    appr_v2 = _approve_at_rate(s_v2, default[te], eq_rate)
    validated = bool(auc_v2 > auc_v1 + 0.005 and appr_v2.mean() >= appr_v1.mean())
    path = get_settings().data_dir / "models" / "ebm_v2.pkl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(ebm, fh)
    terms = {}
    glob = ebm.explain_global().data()
    for name, imp in zip(glob["names"], glob["scores"]):
        terms[name] = round(float(imp), 4)
    metrics = {"test_n": int(len(te)), "auc_v1": round(auc_v1, 4), "auc_v2": round(auc_v2, 4),
               "approval_at_equal_default_v1": round(float(appr_v1.mean()), 4),
               "approval_at_equal_default_v2": round(float(appr_v2.mean()), 4), "term_importance": terms}
    mv = db.scalar(select(ModelVersion).where(ModelVersion.version == "v2"))
    if not mv:
        mv = ModelVersion(version="v2", kind="ebm", is_active=False)
        db.add(mv)
    mv.features = [{"pillar": k, "monotone": "non-decreasing"} for k in C.PILLAR_WEIGHTS]
    mv.weights = {"term_importance": terms, "output": "score = round(100 x P(no default)); bands use the same cut-offs as v1"}
    mv.training_data = {"description": f"{len(tr)} simulated workers (70% split of the latest validation run); label = no default "
                                       "in 26 simulated weeks after scoring; inputs = the five pillar scores only.",
                        "source": "simulated", "seed": seed}
    mv.metrics = metrics
    mv.validated = validated
    mv.artifact_path = str(path)
    mv.notes = ("Explainable Boosting Machine with monotonic (non-decreasing) constraints on all five pillars. "
                + ("It beat v1 on the held-out comparison; an admin can make it active."
                   if validated else
                   "It did NOT beat v1 on the held-out comparison (AUC and approvals at equal default rate), so v1 stays active."))
    if not validated and mv.is_active:
        model_registry.activate(db, C.MODEL_VERSION_V1)
    db.flush()
    return metrics | {"validated": validated}
