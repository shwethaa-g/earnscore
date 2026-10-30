"""Scoring engine (BUILD.md section 6) as pure functions over a ScoringInput.

ScoringInput is built from reconciled ledger rows (app/services/snapshots.py) or directly by the
validation simulator (app/sim/simulate.py). Every constant comes from scoring/config.py.
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.scoring import config as C


# ---------------------------------------------------------------- inputs

@dataclass
class Event:
    id: int
    date: date
    amount: float
    key: str = ""        # stream (platform / payer) for income, payee for bills, category for essentials
    category: str = ""
    hours: float | None = None
    matched: bool = False
    source_id: int = 0
    balance: float | None = None
    flag: str = ""


@dataclass
class ScoringInput:
    as_of: date
    weeks: list[date]                      # Mondays, ascending, contiguous
    earned: list[float]                    # counted earned income per week
    hours: list[float | None]              # active hours per week (platform statements), None if unknown
    income: list[Event] = field(default_factory=list)      # counted earned credits (key = stream)
    essentials: list[Event] = field(default_factory=list)  # rent / utilities / fuel / emi debits (category)
    bills: list[Event] = field(default_factory=list)       # rent / utilities / emi debits (key = payee)
    bounces: list[Event] = field(default_factory=list)
    savings: list[Event] = field(default_factory=list)
    spend: list[Event] = field(default_factory=list)       # all expense debits (for daily spend)
    balances: list[Event] = field(default_factory=list)    # rows carrying a running balance (source_id, balance)
    payouts: list[Event] = field(default_factory=list)     # platform statement payouts (matched flag)
    flagged: list[Event] = field(default_factory=list)     # ledger rows carrying an anti-gaming flag (flag)
    large_credits: list[Event] = field(default_factory=list)  # credits that could inflate income (for pre-application check)
    first_date: date | None = None
    n_sources: int = 0
    cohort_index: dict[int, float] | None = None
    cohort_n: int = 0


# ---------------------------------------------------------------- helpers

def curve(name: str, x: float) -> float:
    pts = C.CURVES[name]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if xs[0] > xs[-1]:
        xs, ys = xs[::-1], ys[::-1]
    return float(np.interp(x, xs, ys))


def band_for(score: float) -> str:
    for b, lo in C.BANDS:
        if score >= lo:
            return b
    return C.BANDS[-1][0]


def _window(inp: ScoringInput, weeks: int) -> tuple[list[date], np.ndarray]:
    complete = [(w, y) for w, y in zip(inp.weeks, inp.earned) if w + timedelta(days=6) <= inp.as_of]
    complete = complete[-weeks:]
    return [w for w, _ in complete], np.array([y for _, y in complete], dtype=float)


def _in_days(events: list[Event], as_of: date, days: int) -> list[Event]:
    start = as_of - timedelta(days=days)
    return [e for e in events if start < e.date <= as_of]


# ---------------------------------------------------------------- seasonality

def seasonal_adjust(weeks: list[date], y: np.ndarray, cohort_index: dict[int, float] | None, cohort_n: int) -> dict:
    """Return adjusted, residual and seasonal arrays plus the method used (BUILD.md 6.1)."""
    s = pd.Series(y, index=pd.to_datetime(weeks))
    n = len(y)
    if n >= C.STL_MIN_WEEKS:
        from statsmodels.tsa.seasonal import STL

        res = STL(s, period=C.STL_PERIOD, robust=True, seasonal_deg=C.STL_SEASONAL_DEG).fit()
        seasonal = res.seasonal.to_numpy()
        return {"method": "stl", "seasonal": seasonal, "adjusted": y - seasonal, "residual": res.resid.to_numpy()}
    if cohort_index and cohort_n >= C.COHORT_MIN_WORKERS and n > 0:
        idx = np.array([cohort_index.get(w.isocalendar()[1], cohort_index.get(52, 1.0)) for w in weeks], dtype=float)
        idx = np.where(idx <= 0.05, 0.05, idx)
        adjusted = y / idx
        trend = pd.Series(adjusted).rolling(C.TREND_WINDOW, center=True, min_periods=1).median().to_numpy()
        return {"method": "cohort", "seasonal": y - adjusted, "adjusted": adjusted, "residual": adjusted - trend}
    trend = s.rolling(C.MOVING_MEDIAN_WINDOW, center=True, min_periods=1).median().to_numpy()
    return {"method": "moving_median", "seasonal": np.zeros(n), "adjusted": y.copy(), "residual": y - trend}


def cohort_index_from(series_by_worker: list[tuple[list[date], list[float]]]) -> tuple[dict[int, float], int]:
    """Multiplicative week-of-year index (mean 1) from workers' weekly earned income. Pure; used by services/cohort.py."""
    per_week: dict[int, list[float]] = defaultdict(list)
    n = 0
    for weeks, ys in series_by_worker:
        arr = np.array(ys, dtype=float)
        if len(arr) < C.COHORT_MIN_WEEKS or arr.mean() <= 0:
            continue
        n += 1
        norm = arr / arr.mean()
        for w, v in zip(weeks, norm):
            per_week[w.isocalendar()[1]].append(float(v))
    if n == 0:
        return {}, 0
    # mean (not median) of normalised income per week-of-year: with many zero-income weeks a median collapses to 0
    raw = np.array([float(np.mean(per_week[k])) if per_week.get(k) else 1.0 for k in range(1, 54)])
    smooth = (np.roll(raw, 1) + raw + np.roll(raw, -1)) / 3.0
    smooth = smooth / smooth[:52].mean()
    smooth = np.clip(smooth, *C.COHORT_INDEX_BOUNDS)
    smooth = smooth / smooth[:52].mean()
    return {k: round(float(smooth[k - 1]), 4) for k in range(1, 54)}, n


# ---------------------------------------------------------------- features

def extract_features(inp: ScoringInput) -> tuple[dict, dict, dict]:
    """Return (features, evidence ids per sub-metric, chart series)."""
    feats: dict = {}
    ev: dict[str, list[int]] = {}
    as_of = inp.as_of

    full_weeks, full_y = _window(inp, 156)
    weeks, y = _window(inp, C.LOOKBACK_WEEKS)
    mean_y = float(y.mean()) if len(y) else 0.0
    adj = seasonal_adjust(full_weeks, full_y, inp.cohort_index, inp.cohort_n) if len(full_y) else \
        {"method": "moving_median", "seasonal": np.array([]), "adjusted": np.array([]), "residual": np.array([])}
    k = len(y)
    resid = adj["residual"][-k:] if k else np.array([])
    adjusted = adj["adjusted"][-k:] if k else np.array([])
    feats["seasonality_method"] = adj["method"]

    win_start = weeks[0] if weeks else as_of - timedelta(weeks=C.LOOKBACK_WEEKS)
    income_w = [e for e in inp.income if win_start <= e.date <= as_of]

    # Consistency
    feats["active_week_share"] = float((y > 0).mean()) if k else 0.0
    ev["active_week_share"] = [e.id for e in income_w]
    dates = sorted({e.date for e in income_w})
    if dates:
        bounds = [win_start] + dates + [as_of]
        gaps = [((bounds[i + 1] - bounds[i]).days, i) for i in range(len(bounds) - 1)]
        gap, gi = max(gaps)
        feats["longest_gap_days"] = float(gap)
        edge = {bounds[gi], bounds[gi + 1]}
        ev["longest_gap_days"] = [e.id for e in income_w if e.date in edge]
    else:
        feats["longest_gap_days"] = float((as_of - win_start).days)
        ev["longest_gap_days"] = []
    streams: dict[str, list[Event]] = defaultdict(list)
    for e in income_w:
        streams[e.key].append(e)
    cvs, wts = [], []
    for key, evs in streams.items():
        ds = sorted({e.date for e in evs})
        if len(ds) >= 4:
            g = np.diff([d.toordinal() for d in ds]).astype(float)
            cvs.append(float(g.std() / g.mean()) if g.mean() > 0 else 0.0)
            wts.append(sum(e.amount for e in evs))
    feats["payout_gap_cv"] = float(np.average(cvs, weights=wts)) if cvs else None
    ev["payout_gap_cv"] = [e.id for e in income_w]

    # Stability
    feats["v_raw"] = float(y.std() / mean_y) if mean_y > 0 else 1.0
    feats["v_res"] = float(resid.std() / mean_y) if mean_y > 0 and k > 1 else 1.0
    feats["downside_dev"] = float(math.sqrt(float(np.mean(np.minimum(resid, 0) ** 2))) / mean_y) if mean_y > 0 and k else 1.0
    if k >= 4 and mean_y > 0:
        p20 = float(np.quantile(adjusted, C.F20_QUANTILE))
        episodes, run = [], 0
        for v in adjusted:
            if v < p20:
                run += 1
            elif run:
                episodes.append(run)
                run = 0
        if run:
            episodes.append(run)
        feats["recovery_weeks"] = float(statistics.median(episodes)) if episodes else 1.0
        worst = set(np.argsort(resid)[:5].tolist())
        dip_weeks = {weeks[i] for i in worst}
        ev["v_res"] = ev["downside_dev"] = [e.id for e in income_w if e.date - timedelta(days=e.date.weekday()) in dip_weeks]
        low = {weeks[i] for i, v in enumerate(adjusted) if v < p20}
        ev["recovery_weeks"] = [e.id for e in income_w if e.date - timedelta(days=e.date.weekday()) in low]
    else:
        feats["recovery_weeks"] = 8.0
        ev["v_res"] = ev["downside_dev"] = ev["recovery_weeks"] = []

    # Capacity
    _, y26 = _window(inp, C.F20_WEEKS)
    f20 = float(np.quantile(y26, C.F20_QUANTILE)) if len(y26) else 0.0
    med26 = float(np.median(y26)) if len(y26) else 0.0
    ess_days = min(C.ESSENTIALS_WEEKS * 7, max((as_of - (inp.first_date or as_of)).days, 7))
    ess = _in_days(inp.essentials, as_of, ess_days)
    parts = defaultdict(float)
    for e in ess:
        parts[e.category] += e.amount
    weeks_n = ess_days / 7.0
    e_parts = {c: round(parts.get(c, 0.0) / weeks_n, 2) for c in ("rent", "utilities", "fuel", "emi")}
    e_ess = round(sum(e_parts.values()), 2)
    feats.update(f20=round(f20, 2), e_ess=e_ess, e_ess_parts=e_parts, median_week=round(med26, 2))
    feats["capacity_share"] = float(np.clip((f20 - e_ess) / f20, 0, 1)) if f20 > 0 else 0.0
    feats["dsr"] = float(e_parts["emi"] / med26) if med26 > 0 else (1.0 if e_parts["emi"] > 0 else 0.0)
    bad_weeks = set()
    if len(y26):
        w26, _ = _window(inp, C.F20_WEEKS)
        bad_weeks = {w for w, v in zip(w26, y26) if v <= f20}
    ev["capacity_share"] = [e.id for e in ess] + [e.id for e in inp.income if e.date - timedelta(days=e.date.weekday()) in bad_weeks]
    ev["dsr"] = [e.id for e in ess if e.category == "emi"]

    # Discipline
    b = _in_days(inp.bounces, as_of, C.BOUNCE_WEEKS * 7)
    feats["bounces"] = float(len(b))
    ev["bounces"] = [e.id for e in b]
    feats["on_time_rate"], ev["on_time_rate"] = _on_time(inp.bills, as_of)
    feats["buffer_days"], ev["buffer_days"] = _buffer(inp, as_of)
    months_hist = max(1, min(C.SAVINGS_MONTHS, round(((as_of - (inp.first_date or as_of)).days) / 30.44)))
    sv = _in_days(inp.savings, as_of, months_hist * 30)
    feats["savings_rate"] = min(1.0, len({(e.date.year, e.date.month) for e in sv}) / months_hist)
    ev["savings_rate"] = [e.id for e in sv]

    # Resilience
    inc26 = _in_days(inp.income, as_of, C.F20_WEEKS * 7)
    tot = sum(e.amount for e in inc26)
    by_stream = defaultdict(float)
    for e in inc26:
        by_stream[e.key] += e.amount
    feats["hhi"] = float(sum((v / tot) ** 2 for v in by_stream.values())) if tot > 0 else None
    feats["platform_count"] = len(by_stream)
    ev["hhi"] = [e.id for e in inc26]
    ten, tw = [], []
    all_streams = defaultdict(list)
    for e in inp.income:
        if e.date <= as_of:
            all_streams[e.key].append(e)
    for key, evs in all_streams.items():
        if len(evs) >= 4:
            ds = [e.date for e in evs]
            ten.append((max(ds) - min(ds)).days / 30.44)
            tw.append(sum(e.amount for e in evs))
    feats["tenure_months"] = float(np.average(ten, weights=tw)) if ten else 0.0
    ev["tenure_months"] = ev["hhi"]
    w26, _ = _window(inp, C.F20_WEEKS)
    hours_map = {w: h for w, h in zip(inp.weeks, inp.hours)}
    earned_map = {w: v for w, v in zip(inp.weeks, inp.earned)}
    pts = [(i, earned_map[w] / hours_map[w]) for i, w in enumerate(w26) if hours_map.get(w) and earned_map.get(w, 0) > 0]
    if len(pts) >= 8:
        xs = np.array([p[0] for p in pts], dtype=float)
        es = np.array([p[1] for p in pts], dtype=float)
        slope = float(np.polyfit(xs, es, 1)[0])
        feats["eph_trend"] = float(slope * 13 / es.mean()) if es.mean() > 0 else 0.0
    else:
        feats["eph_trend"] = None
    hrs = [hours_map[w] for w in w26 if hours_map.get(w) is not None]
    feats["avg_hours"] = round(float(np.mean(hrs)), 1) if hrs else None
    feats["weeks_over_60"] = int(sum(1 for h in hrs if h > C.OVERWORK_HOURS))
    hour_ids = [e.id for e in inp.payouts if e.hours is not None and e.date >= (w26[0] if w26 else as_of)]
    ev["eph_trend"] = hour_ids
    ev["overwork"] = [e.id for e in inp.payouts if e.hours is not None and
                      hours_map.get(e.date - timedelta(days=e.date.weekday()), 0) and
                      hours_map[e.date - timedelta(days=e.date.weekday())] > C.OVERWORK_HOURS]

    # Data sufficiency inputs
    feats["months"] = round(((as_of - inp.first_date).days / 30.44) if inp.first_date else 0.0, 1)
    feats["n_sources"] = inp.n_sources
    p52 = _in_days(inp.payouts, as_of, 364)
    feats["n_payouts"] = len(p52)
    feats["reconcile_rate"] = (sum(1 for e in p52 if e.matched) / len(p52)) if p52 else 0.0
    feats["mean_week"] = round(mean_y, 2)

    series = {
        "weeks": [w.isoformat() for w in weeks],
        "raw": [round(float(v), 2) for v in y],
        "adjusted": [round(float(v), 2) for v in adjusted],
        "seasonal": [round(float(v), 2) for v in (adj["seasonal"][-k:] if k else [])],
        "hours": [hours_map.get(w) for w in weeks],
    }
    for key in ev:
        ev[key] = ev[key][: C.MAX_EVIDENCE_IDS]
    return feats, ev, series


def _payee(e: Event) -> str:
    return f"{e.category}:{e.key}"


def _on_time(bills: list[Event], as_of: date) -> tuple[float | None, list[int]]:
    start = as_of - timedelta(days=C.BILL_MONTHS * 30)
    groups: dict[str, list[Event]] = defaultdict(list)
    for e in bills:
        if start < e.date <= as_of:
            groups[_payee(e)].append(e)
    expected = on_time = 0
    late_ids, all_ids = [], []
    for evs in groups.values():
        if len(evs) < 2:
            continue
        usual = statistics.median(e.date.day for e in evs)
        by_month: dict[tuple[int, int], list[Event]] = defaultdict(list)
        for e in evs:
            by_month[(e.date.year, e.date.month)].append(e)
        first, last = min(by_month), max(by_month)
        y, m = first
        while (y, m) <= last:
            expected += 1
            pays = by_month.get((y, m), [])
            if any(p.date.day <= usual + C.BILL_GRACE_DAYS for p in pays):
                on_time += 1
            else:
                late_ids.extend(p.id for p in pays)
            m += 1
            if m > 12:
                y, m = y + 1, 1
        all_ids.extend(e.id for e in evs)
    if expected == 0:
        return None, []
    return on_time / expected, late_ids + [i for i in all_ids if i not in set(late_ids)]


def _buffer(inp: ScoringInput, as_of: date) -> tuple[float | None, list[int]]:
    start = as_of - timedelta(days=C.BUFFER_DAYS_WINDOW)
    rows = sorted((e for e in inp.balances if e.balance is not None and e.date <= as_of), key=lambda e: (e.date, e.id))
    if not rows:
        return None, []
    per_source: dict[int, dict[date, float]] = defaultdict(dict)
    for e in rows:
        per_source[e.source_id][e.date] = e.balance  # last balance of the day wins
    days = [start + timedelta(days=i) for i in range(1, C.BUFFER_DAYS_WINDOW + 1)]
    totals = np.zeros(len(days))
    for src, bal in per_source.items():
        ds = sorted(bal)
        cur, j = None, 0
        for i, d in enumerate(days):
            while j < len(ds) and ds[j] <= d:
                cur = bal[ds[j]]
                j += 1
            totals[i] += cur if cur is not None else 0.0
    spend = sum(e.amount for e in inp.spend if start < e.date <= as_of) / C.BUFFER_DAYS_WINDOW
    ids = [e.id for e in rows if e.date > start]
    if spend <= 0:
        return 30.0, ids
    return float(max(totals.mean(), 0.0) / spend), ids


# ---------------------------------------------------------------- pillars and score

def sub_scores(f: dict) -> dict[str, dict[str, dict]]:
    def sc(curve_name: str, value):
        if value is None:
            return {"value": None, "score": C.NEUTRAL_SUBSCORE, "measured": False}
        return {"value": round(float(value), 4), "score": round(curve(curve_name, float(value)), 2), "measured": True}

    out = {
        "consistency": {
            "active_week_share": sc("active_week_share", f["active_week_share"]),
            "longest_gap_days": sc("longest_gap_days", f["longest_gap_days"]),
            "payout_gap_cv": sc("payout_gap_cv", f["payout_gap_cv"]),
        },
        "stability": {
            "v_res": sc("one_minus_v_res", 1 - f["v_res"]) | {"value": round(f["v_res"], 4)},
            "downside_dev": sc("downside_dev", f["downside_dev"]),
            "recovery_weeks": sc("recovery_weeks", f["recovery_weeks"]),
        },
        "capacity": {
            "capacity_share": sc("capacity_share", f["capacity_share"]),
            "dsr": sc("dsr", f["dsr"]),
        },
        "discipline": {
            "bounces": sc("bounces", f["bounces"]),
            "on_time_rate": sc("on_time_rate", f["on_time_rate"]),
            "buffer_days": sc("buffer_days", f["buffer_days"]),
            "savings_rate": sc("savings_rate", f["savings_rate"]),
        },
        "resilience": {
            "hhi": sc("hhi", f["hhi"]),
            "tenure_months": sc("tenure_months", f["tenure_months"]),
            "eph_trend": sc("eph_trend", f["eph_trend"]),
        },
    }
    return out


def score_features(f: dict) -> dict:
    """Pillars (0-100 each), weighted EarnScore and band. This is the v1 expert scorecard."""
    subs = sub_scores(f)
    pillars = {}
    for p, comps in subs.items():
        val = sum(C.SUB_WEIGHTS[p][k] * comps[k]["score"] for k in comps)
        pillars[p] = {"score": round(val, 2), "weight": C.PILLAR_WEIGHTS[p],
                      "contribution": round(C.PILLAR_WEIGHTS[p] * val, 2), "components": comps}
    total = int(round(sum(C.PILLAR_WEIGHTS[p] * pillars[p]["score"] for p in pillars)))
    return {"pillars": pillars, "score": total, "band": band_for(total)}


def data_sufficiency(months: float, sources: int, reconcile_rate: float) -> dict:
    parts = {
        "months": round(C.DSI_WEIGHTS["months"] * min(months / C.DSI_MONTHS_FULL, 1), 4),
        "sources": round(C.DSI_WEIGHTS["sources"] * min(sources / C.DSI_SOURCES_FULL, 1), 4),
        "reconcile_rate": round(C.DSI_WEIGHTS["reconcile_rate"] * max(0.0, min(reconcile_rate, 1.0)), 4),
    }
    return {"dsi": round(sum(parts.values()), 4), "parts": parts,
            "inputs": {"months": months, "sources": sources, "reconcile_rate": round(reconcile_rate, 4)}}


def confidence_for(dsi: float, seasonality_method: str) -> str:
    level = next(name for name, lo in C.CONFIDENCE_LEVELS if dsi >= lo)
    if seasonality_method == "moving_median" and level == "High":
        level = C.FALLBACK_CONFIDENCE_CAP
    return level


def safe_emi(f20: float, e_ess: float, alpha: float = C.DEFAULT_ALPHA) -> dict:
    headroom = f20 - e_ess
    return {"safe_emi": round(max(alpha * headroom, 0.0), 0), "capacity_warning": f20 <= e_ess, "alpha": alpha}


def anti_gaming_flags(inp: ScoringInput, median_week: float) -> list[dict]:
    flags: dict[str, dict] = {}
    for e in _in_days(inp.flagged, inp.as_of, C.F20_WEEKS * 7):
        f = flags.setdefault(e.flag, {"flag": e.flag, "count": 0, "evidence_ids": []})
        f["count"] += 1
        f["evidence_ids"].append(e.id)
    if median_week > 0:
        recent = [e for e in _in_days(inp.large_credits, inp.as_of, C.PRE_APPLICATION_DAYS)
                  if e.amount > C.LARGE_CREDIT_MULTIPLE * median_week]
        if recent:
            flags["large_recent_credit"] = {"flag": "large_recent_credit", "count": len(recent), "evidence_ids": [e.id for e in recent]}
    return list(flags.values())


def routing(band: str, confidence: str, flags: list[dict]) -> dict:
    reasons = []
    if band in C.MANUAL_REVIEW_BANDS:
        reasons.append(f"band_{band}")
    if confidence == "Low":
        reasons.append("low_confidence")
    if flags:
        reasons.append("anti_gaming_flags")
    return {"status": "manual_review_required" if reasons else "submitted", "reasons": reasons,
            "suggested_outcome": "review" if reasons else "approve"}


def watchouts(f: dict, emi: dict, flags: list[dict]) -> list[dict]:
    out = []
    if f.get("weeks_over_60"):
        out.append({"code": "OVERWORK_RISK", "params": {"weeks": f["weeks_over_60"], "hours": int(C.OVERWORK_HOURS)}})
    if emi["capacity_warning"]:
        out.append({"code": "CAPACITY_WARNING", "params": {"f20": f["f20"], "e_ess": f["e_ess"]}})
    for fl in flags:
        out.append({"code": f"FLAG_{fl['flag'].upper()}", "params": {"count": fl["count"]}})
    return out


SUB_TO_CODE = {
    "active_week_share": "ACTIVE_WEEKS", "longest_gap_days": "LONGEST_GAP", "payout_gap_cv": "PAYOUT_REGULARITY",
    "v_res": "UNEXPLAINED_SWING", "downside_dev": "DOWNSIDE_DEVIATION", "recovery_weeks": "RECOVERY_SPEED",
    "capacity_share": "BAD_WEEK_HEADROOM", "dsr": "DEBT_SERVICE",
    "bounces": "BOUNCED_DEBITS", "on_time_rate": "ON_TIME_BILLS", "buffer_days": "CASH_BUFFER", "savings_rate": "REGULAR_SAVINGS",
    "hhi": "INCOME_CONCENTRATION", "tenure_months": "PLATFORM_TENURE", "eph_trend": "EARNINGS_PER_HOUR",
}


def reason_codes(result: dict, f: dict, evidence: dict) -> list[dict]:
    """One reason per measured sub-metric that is clearly strong or weak, ordered by impact on the score."""
    out = []
    for p, pdata in result["pillars"].items():
        for sub, comp in pdata["components"].items():
            if not comp["measured"]:
                continue
            s = comp["score"]
            if C.REASON_WEAK <= s < C.REASON_STRONG:
                continue
            impact = round(C.PILLAR_WEIGHTS[p] * C.SUB_WEIGHTS[p][sub] * (s - C.NEUTRAL_SUBSCORE), 2)
            params = {"value": comp["value"], "sub_score": s}
            extra = {"capacity_share": {"f20": f["f20"], "e_ess": f["e_ess"]},
                     "v_res": {"v_raw": round(f["v_raw"], 4)}, "dsr": {"emi_week": f["e_ess_parts"]["emi"]}}
            params.update(extra.get(sub, {}))
            code = f"{SUB_TO_CODE[sub]}_{'POS' if s >= C.REASON_STRONG else 'NEG'}"
            value = comp["value"]
            if sub == "dsr" and value == 0:
                code = "DEBT_SERVICE_NONE"
            elif sub == "savings_rate" and value == 0:
                code = "REGULAR_SAVINGS_NONE"
            elif sub == "buffer_days" and value is not None and value < 1:
                code = "CASH_BUFFER_NONE"
            out.append({"code": code, "pillar": p,
                        "direction": "positive" if s >= C.REASON_STRONG else "negative", "impact": impact,
                        "sub": sub, "params": params, "evidence_ids": evidence.get(sub, [])})
    out.sort(key=lambda r: -abs(r["impact"]))
    return out


def run(inp: ScoringInput, alpha: float = C.DEFAULT_ALPHA) -> dict:
    """Full v1 scoring run over one ScoringInput. Pure: same input, same output."""
    f, ev, series = extract_features(inp)
    result = score_features(f)
    dsi = data_sufficiency(f["months"], f["n_sources"], f["reconcile_rate"])
    conf = confidence_for(dsi["dsi"], f["seasonality_method"])
    emi = safe_emi(f["f20"], f["e_ess"], alpha)
    flags = anti_gaming_flags(inp, f["median_week"])
    route = routing(result["band"], conf, flags)
    return {"features": f, "evidence": ev, "series": series, **result, "dsi": dsi, "confidence": conf, "emi": emi,
            "flags": flags, "routing": route, "watchouts": watchouts(f, emi, flags),
            "reasons": reason_codes(result, f, ev)}
