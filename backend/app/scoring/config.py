"""Every scoring constant lives here (BUILD.md section 6). Nothing is inlined in the scoring functions.

Curves are piecewise-linear: a list of (x, score) points, interpolated and clipped at the ends.
"""

MODEL_VERSION_V1 = "v1"
CONFIG_VERSION = "2026.10.3"

PILLAR_WEIGHTS = {"consistency": 0.25, "stability": 0.25, "capacity": 0.25, "discipline": 0.15, "resilience": 0.10}

BANDS = [("A", 80), ("B", 65), ("C", 50), ("D", 35), ("E", 0)]  # band, minimum score

# --- windows (weeks / days) ---
LOOKBACK_WEEKS = 52          # consistency, stability, resilience
F20_WEEKS = 26               # bad-week floor
ESSENTIALS_WEEKS = 26
BOUNCE_WEEKS = 26
BILL_MONTHS = 6
BUFFER_DAYS_WINDOW = 56      # 8 weeks, so recourse text "for 8 weeks" is literally true
SAVINGS_MONTHS = 6
STL_MIN_WEEKS = 104          # two years
STL_PERIOD = 52
COHORT_MIN_WORKERS = 20
COHORT_MIN_WEEKS = 26        # a worker needs this much history to contribute to a cohort index
COHORT_INDEX_BOUNDS = (0.5, 2.0)  # a week-of-year index outside this range is clipped (guards against zero-heavy cohorts)
STL_SEASONAL_DEG = 0         # seasonal shape constant across years: only what repeats counts as seasonal
MOVING_MEDIAN_WINDOW = 4
TREND_WINDOW = 9             # rolling median used as trend when the cohort index is used
F20_QUANTILE = 0.20
PRE_APPLICATION_DAYS = 14
LARGE_CREDIT_MULTIPLE = 3.0
OVERWORK_HOURS = 60.0
BILL_GRACE_DAYS = 5

# --- sub-metric weights inside each pillar ---
SUB_WEIGHTS = {
    "consistency": {"active_week_share": 0.5, "longest_gap_days": 0.25, "payout_gap_cv": 0.25},
    "stability": {"v_res": 0.5, "downside_dev": 0.25, "recovery_weeks": 0.25},
    "capacity": {"capacity_share": 0.75, "dsr": 0.25},
    "discipline": {"bounces": 0.30, "on_time_rate": 0.25, "buffer_days": 0.30, "savings_rate": 0.15},
    "resilience": {"hhi": 0.40, "tenure_months": 0.30, "eph_trend": 0.30},
}

# --- curves: (feature value, sub-score) ---
CURVES = {
    "active_week_share": [(0.5, 0), (0.75, 50), (0.9, 80), (1.0, 100)],
    "longest_gap_days": [(7, 100), (14, 80), (28, 50), (56, 0)],
    "payout_gap_cv": [(0.0, 100), (0.5, 70), (1.0, 35), (1.5, 0)],
    # 1 - V_res mapped piecewise-linearly (BUILD.md 6.2)
    "one_minus_v_res": [(0.2, 0), (0.5, 40), (0.7, 70), (0.85, 90), (1.0, 100)],
    "downside_dev": [(0.0, 100), (0.1, 80), (0.25, 40), (0.5, 0)],
    "recovery_weeks": [(1, 100), (2, 80), (4, 50), (8, 0)],
    "capacity_share": [(0.0, 0), (0.2, 40), (0.4, 70), (0.6, 100)],
    "dsr": [(0.0, 100), (0.15, 80), (0.3, 40), (0.5, 0)],
    "bounces": [(0, 100), (1, 60), (2, 30), (3, 0)],
    "on_time_rate": [(0.5, 0), (0.8, 60), (0.95, 90), (1.0, 100)],
    "buffer_days": [(0, 0), (3, 30), (7, 60), (14, 85), (30, 100)],
    "savings_rate": [(0.0, 0), (0.5, 60), (1.0, 100)],
    "hhi": [(0.5, 100), (0.8, 70), (1.0, 50)],
    "tenure_months": [(0, 0), (3, 30), (6, 55), (12, 80), (24, 100)],
    "eph_trend": [(-0.2, 0), (-0.05, 50), (0.0, 65), (0.1, 100)],
}
# Used when a sub-metric cannot be measured from the data the worker supplied (unknown is not bad).
NEUTRAL_SUBSCORE = 50.0

# --- Data Sufficiency (separate; never part of the score) ---
DSI_WEIGHTS = {"months": 0.4, "sources": 0.3, "reconcile_rate": 0.3}
DSI_MONTHS_FULL = 12
DSI_SOURCES_FULL = 3
CONFIDENCE_LEVELS = [("High", 0.7), ("Medium", 0.4), ("Low", 0.0)]
# When seasonality falls back to the moving median (cohort too small), confidence is capped at this level.
FALLBACK_CONFIDENCE_CAP = "Medium"

# --- Safe EMI ---
DEFAULT_ALPHA = 0.5

# --- Routing ---
MANUAL_REVIEW_BANDS = {"D", "E"}

# --- Reason codes: a sub-score at or above this is a strength, below the low mark a weakness ---
REASON_STRONG = 65.0
REASON_WEAK = 50.0
MAX_EVIDENCE_IDS = 400

# --- Recourse: only these features may change; candidate values searched ---
RECOURSE_ACTIONABLE = {
    "buffer_days": [7, 10, 14, 21, 30],
    "on_time_rate": [0.9, 0.95, 1.0],
    "bounces": [0],
    "active_week_share": [0.05, 0.10, 0.15],  # increments, capped at 1.0
}
RECOURSE_LOCKED = ["active_hours", "platform_count", "income_level", "hhi", "tenure_months"]
RECOURSE_MAX_STEPS = 3
