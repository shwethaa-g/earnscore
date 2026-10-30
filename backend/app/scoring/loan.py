"""Suggested loan shape: weekly EMI on the usual payout day, with a seasonal skip-week."""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SKIP_WEEKS_PER_YEAR = 1


def payout_day(income_dates: list[date]) -> str:
    if not income_dates:
        return ""
    return WEEKDAYS[Counter(d.weekday() for d in income_dates).most_common(1)[0][0]]


def skip_weeks(start: date, tenure_weeks: int, seasonal_index: dict[int, float] | None) -> list[str]:
    """Week(s) inside the tenure with the lowest expected seasonal income (Monday dates, ISO strings)."""
    if not seasonal_index:
        return []
    weeks = [start + timedelta(weeks=i) for i in range(tenure_weeks)]
    per_year = max(1, tenure_weeks // 52) * SKIP_WEEKS_PER_YEAR
    ranked = sorted(weeks, key=lambda w: (seasonal_index.get(w.isocalendar()[1], 1.0), w))
    return sorted(w.isoformat() for w in ranked[:per_year])


def principal_for(weekly_emi: float, tenure_weeks: int, annual_rate: float, n_skips: int = 0) -> float:
    """Present value of the paying weeks at the lender's weekly rate."""
    n = max(tenure_weeks - n_skips, 0)
    if weekly_emi <= 0 or n == 0:
        return 0.0
    r = annual_rate / 52.0
    if r == 0:
        return round(weekly_emi * n, 0)
    return round(weekly_emi * (1 - (1 + r) ** -n) / r, 0)


def emi_for(principal: float, tenure_weeks: int, annual_rate: float, n_skips: int = 0) -> float:
    n = max(tenure_weeks - n_skips, 1)
    r = annual_rate / 52.0
    if r == 0:
        return round(principal / n, 0)
    return round(principal * r / (1 - (1 + r) ** -n), 0)


def suggest(safe_emi: float, requested_amount: float, requested_tenure: int, annual_rate: float,
            income_dates: list[date], seasonal_index: dict[int, float] | None, start: date) -> dict:
    skips = skip_weeks(start, requested_tenure, seasonal_index)
    needed = emi_for(requested_amount, requested_tenure, annual_rate, len(skips))
    emi = min(needed, safe_emi)
    amount = requested_amount if needed <= safe_emi else principal_for(safe_emi, requested_tenure, annual_rate, len(skips))
    return {"payout_day": payout_day(income_dates), "weekly_emi": emi, "tenure_weeks": requested_tenure,
            "amount": amount, "skip_weeks": skips, "requested_emi": needed,
            "fits_safe_emi": needed <= safe_emi, "annual_rate": annual_rate}
