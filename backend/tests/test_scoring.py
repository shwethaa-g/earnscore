from datetime import date, timedelta

import numpy as np
import pytest

from app.scoring import config as C
from app.scoring import engine, loan, recourse
from app.scoring.engine import Event, ScoringInput


def weeks_from(n, end=date(2026, 10, 19)):
    return [end - timedelta(weeks=n - 1 - i) for i in range(n)]


def make_input(y, hours=None, **kw):
    ws = weeks_from(len(y))
    inc = []
    for i, (w, v) in enumerate(zip(ws, y)):
        if v > 0:
            inc.append(Event(i + 1, w + timedelta(days=2), float(v), key="Swiggy"))
    defaults = dict(as_of=ws[-1] + timedelta(days=6), weeks=ws, earned=list(map(float, y)),
                    hours=hours or [None] * len(y), income=inc, first_date=ws[0], n_sources=2)
    defaults.update(kw)
    return ScoringInput(**defaults)


def seasonal_series(n, amp=0.3, noise=0.05, seed=1):
    rng = np.random.default_rng(seed)
    ws = weeks_from(n)
    return np.array([5000 * (1 + amp * np.sin(2 * np.pi * w.isocalendar()[1] / 52)) * (1 + rng.normal(0, noise)) for w in ws])


# ---------- seasonality

def test_stl_removes_predictable_seasonality():
    y = seasonal_series(110)
    f, _, _ = engine.extract_features(make_input(y))
    assert f["seasonality_method"] == "stl"
    assert f["v_res"] < f["v_raw"] / 2
    assert f["v_res"] > 0.01  # noise that does not repeat across years must not be absorbed as "seasonal"


def test_cohort_index_used_for_short_history_and_fallback_when_small():
    y = seasonal_series(40)
    ws = weeks_from(40)
    idx = {w.isocalendar()[1]: 1 + 0.3 * np.sin(2 * np.pi * w.isocalendar()[1] / 52) for w in weeks_from(53)}
    f_c, _, _ = engine.extract_features(make_input(y, cohort_index=idx, cohort_n=C.COHORT_MIN_WORKERS))
    f_m, _, _ = engine.extract_features(make_input(y, cohort_index=idx, cohort_n=C.COHORT_MIN_WORKERS - 1))
    assert f_c["seasonality_method"] == "cohort" and f_m["seasonality_method"] == "moving_median"
    assert f_c["v_res"] < f_c["v_raw"]
    assert len(ws) == 40


def test_cohort_index_from_workers_is_mean_one():
    series = [(weeks_from(60), list(seasonal_series(60, seed=s))) for s in range(25)]
    idx, n = engine.cohort_index_from(series)
    assert n == 25 and abs(np.mean([idx[k] for k in range(1, 53)]) - 1) < 1e-4  # stored rounded to 4 dp


# ---------- pillars

def test_consistency_rewards_active_weeks_and_short_gaps():
    steady = engine.run(make_input([4000] * 52))
    gappy = engine.run(make_input([4000 if i % 3 else 0 for i in range(52)]))
    assert steady["pillars"]["consistency"]["score"] > gappy["pillars"]["consistency"]["score"]
    assert steady["features"]["active_week_share"] == 1.0


def test_stability_penalises_unexplained_volatility():
    rng = np.random.default_rng(3)
    calm = engine.run(make_input(list(4000 * (1 + rng.normal(0, 0.05, 52)))))
    wild = engine.run(make_input(list(np.abs(4000 * (1 + rng.normal(0, 0.6, 52))))))
    assert calm["pillars"]["stability"]["score"] > wild["pillars"]["stability"]["score"]


def test_capacity_uses_bad_week_floor_minus_essentials():
    y = [3000] * 10 + [5000] * 42
    ess = [Event(1000 + i, date(2026, 5, 5) + timedelta(days=30 * i), 4300.0, category="rent") for i in range(6)]
    out = engine.run(make_input(y, essentials=ess))
    f = out["features"]
    assert f["f20"] == pytest.approx(np.quantile(y[-26:], 0.2))
    assert f["e_ess"] > 0 and 0 <= f["capacity_share"] <= 1


def test_income_level_is_not_rewarded():
    small = engine.run(make_input([2000] * 52))
    large = engine.run(make_input([20000] * 52))
    assert small["score"] == large["score"]


def test_discipline_bounces_and_buffer():
    base = make_input([4000] * 52)
    bounced = make_input([4000] * 52, bounces=[Event(900 + i, date(2026, 9, 1) + timedelta(days=i), 590.0) for i in range(3)])
    assert engine.run(base)["pillars"]["discipline"]["score"] > engine.run(bounced)["pillars"]["discipline"]["score"]


def test_resilience_flags_overwork_but_never_rewards_hours():
    y = [4000] * 52
    normal = engine.run(make_input(y, hours=[45.0] * 52))
    long = engine.run(make_input(y, hours=[70.0] * 52))
    assert long["features"]["weeks_over_60"] > 0
    assert any(w["code"] == "OVERWORK_RISK" for w in long["watchouts"])
    assert long["score"] <= normal["score"]


# ---------- score, bands, DSI, EMI, routing

@pytest.mark.parametrize("score,band", [(100, "A"), (80, "A"), (79, "B"), (65, "B"), (64, "C"), (50, "C"), (49, "D"), (35, "D"), (34, "E"), (0, "E")])
def test_bands(score, band):
    assert engine.band_for(score) == band


def test_score_is_weighted_sum_of_pillars():
    out = engine.run(make_input([4000] * 52))
    expect = round(sum(C.PILLAR_WEIGHTS[p] * out["pillars"][p]["score"] for p in C.PILLAR_WEIGHTS))
    assert out["score"] == expect


def test_dsi_formula_and_confidence():
    d = engine.data_sufficiency(6, 1, 0.5)
    assert d["dsi"] == pytest.approx(0.4 * 0.5 + 0.3 * (1 / 3) + 0.3 * 0.5, abs=1e-3)
    assert engine.confidence_for(0.7, "stl") == "High"
    assert engine.confidence_for(0.69, "stl") == "Medium"
    assert engine.confidence_for(0.4, "cohort") == "Medium"
    assert engine.confidence_for(0.39, "cohort") == "Low"
    assert engine.confidence_for(0.95, "moving_median") == "Medium"  # fallback seasonality caps confidence


def test_safe_emi_never_negative():
    assert engine.safe_emi(3000, 1000, 0.5) == {"safe_emi": 1000, "capacity_warning": False, "alpha": 0.5}
    out = engine.safe_emi(1000, 1500, 0.5)
    assert out["safe_emi"] == 0 and out["capacity_warning"]


def test_routing_rules_never_decline():
    assert engine.routing("B", "High", [])["status"] == "submitted"
    for band, conf, flags in [("D", "High", []), ("E", "High", []), ("A", "Low", []), ("A", "High", [{"flag": "round_trip"}])]:
        r = engine.routing(band, conf, flags)
        assert r["status"] == "manual_review_required" and r["suggested_outcome"] == "review"


def test_reason_codes_carry_evidence():
    out = engine.run(make_input([4000 if i % 4 else 0 for i in range(52)]))
    assert out["reasons"]
    assert all(isinstance(r["evidence_ids"], list) for r in out["reasons"])
    assert any(r["evidence_ids"] for r in out["reasons"])


def test_large_recent_credit_flag():
    inp = make_input([4000] * 52)
    inp.large_credits = [Event(5000, inp.as_of - timedelta(days=3), 20000.0)]
    assert any(f["flag"] == "large_recent_credit" for f in engine.run(inp)["flags"])


# ---------- recourse

def test_recourse_steps_are_valid_and_only_touch_actionable_features():
    inp = make_input([4000] * 52, bounces=[Event(900 + i, date(2026, 9, 1) + timedelta(days=i), 590.0) for i in range(3)])
    out = engine.run(inp)
    res = recourse.search(out["features"])
    for s in res["steps"]:
        assert recourse.verify_step(out["features"], s)
        assert recourse.BAND_RANK[s["new_band"]] < recourse.BAND_RANK[res["current_band"]]
        for ch in s["changes"]:
            assert ch["feature"] in C.RECOURSE_ACTIONABLE
            assert ch["feature"] not in C.RECOURSE_LOCKED


def test_recourse_never_suggests_hours_or_platforms():
    assert "active_hours" in C.RECOURSE_LOCKED and "platform_count" in C.RECOURSE_LOCKED
    assert not set(C.RECOURSE_ACTIONABLE) & set(C.RECOURSE_LOCKED)


# ---------- loan shape

def test_loan_shape_payout_day_and_skip_week():
    dates = [date(2026, 6, 3) + timedelta(weeks=i) for i in range(10)]  # Wednesdays
    assert loan.payout_day(dates) == "Wednesday"
    idx = {k: 1.0 for k in range(1, 54)}
    idx[7] = 0.7
    skips = loan.skip_weeks(date(2026, 11, 2), 52, idx)
    assert len(skips) == 1 and date.fromisoformat(skips[0]).isocalendar()[1] == 7
    assert loan.principal_for(1000, 52, 0.24, 1) < 51 * 1000


def test_recourse_steps_use_each_feature_once():
    inp = make_input([4000 if i % 6 else 0 for i in range(52)],
                     bounces=[Event(900 + i, date(2026, 9, 1) + timedelta(days=i), 590.0) for i in range(3)])
    res = recourse.search(engine.run(inp)["features"])
    feats = [c["feature"] for s in res["steps"] for c in s["changes"]]
    assert len(feats) == len(set(feats))


def test_cohort_index_stays_bounded_for_zero_heavy_cohorts():
    rng = np.random.default_rng(5)
    series = [(weeks_from(60), list(np.where(rng.random(60) < 0.5, 0, rng.uniform(2000, 9000, 60)))) for _ in range(25)]
    idx, n = engine.cohort_index_from(series)
    lo, hi = C.COHORT_INDEX_BOUNDS
    assert n == 25 and all(lo * 0.9 <= v <= hi * 1.1 for v in idx.values())
    y = np.array(series[0][1])
    f, _, _ = engine.extract_features(make_input(list(y), cohort_index=idx, cohort_n=n))
    assert f["seasonality_method"] == "cohort" and f["v_res"] <= f["v_raw"] * 1.5
