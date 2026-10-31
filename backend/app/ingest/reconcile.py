"""Reconciliation rule, as pure functions.

A platform payout and a bank credit match when
    |amount_diff| / payout_amount <= 1%  AND  0 <= credit_date - payout_date <= 3 days
    AND the payer ID or narration matches the platform.
Matching is one-to-one; matched pairs count once (the bank credit is the counted side).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.ingest.classify import PLATFORM_PAYERS

AMOUNT_TOLERANCE = 0.01
MAX_LAG_DAYS = 3
ROUND_TRIP_DAYS = 2


@dataclass
class Payout:
    id: int
    date: date
    amount: float
    platform: str


@dataclass
class Credit:
    id: int
    date: date
    amount: float
    narration: str
    platform: str = ""


def payer_matches(platform: str, credit: Credit) -> bool:
    if credit.platform and credit.platform == platform:
        return True
    ids = PLATFORM_PAYERS.get(platform, [platform.upper()])
    text = credit.narration.upper()
    return any(i in text for i in ids)


def is_match(p: Payout, c: Credit) -> bool:
    if p.amount <= 0:
        return False
    lag = (c.date - p.date).days
    return abs(c.amount - p.amount) / p.amount <= AMOUNT_TOLERANCE and 0 <= lag <= MAX_LAG_DAYS and payer_matches(p.platform, c)


def reconcile(payouts: list[Payout], credits: list[Credit]) -> tuple[list[tuple[int, int]], list[int]]:
    """Return (matches as (payout_id, credit_id), unmatched payout ids). Greedy by date, closest lag then amount."""
    by_day: dict[date, list[Credit]] = {}
    for c in credits:
        by_day.setdefault(c.date, []).append(c)
    used: set[int] = set()
    matches: list[tuple[int, int]] = []
    unmatched: list[int] = []
    for p in sorted(payouts, key=lambda x: (x.date, x.id)):
        best, best_key = None, None
        for lag in range(MAX_LAG_DAYS + 1):
            for c in by_day.get(p.date + timedelta(days=lag), []):
                if c.id in used or not is_match(p, c):
                    continue
                key = (lag, abs(c.amount - p.amount), c.id)
                if best_key is None or key < best_key:
                    best, best_key = c, key
        if best is None:
            unmatched.append(p.id)
        else:
            used.add(best.id)
            matches.append((p.id, best.id))
    return matches, unmatched


@dataclass
class Movement:
    id: int
    source_id: int
    date: date
    amount: float
    direction: str


def find_round_trips(moves: list[Movement]) -> set[int]:
    """Credits that mirror an equal debit from another of the worker's own accounts within 2 days.

    These are own-account transfers even if the narration does not say so, and must not count as earned.
    Returns the ids of such credits.
    """
    debits = [m for m in moves if m.direction == "debit"]
    by_amount: dict[float, list[Movement]] = {}
    for d in debits:
        by_amount.setdefault(round(d.amount, 2), []).append(d)
    used: set[int] = set()
    hits: set[int] = set()
    for c in sorted((m for m in moves if m.direction == "credit"), key=lambda x: (x.date, x.id)):
        for d in by_amount.get(round(c.amount, 2), []):
            if d.id in used or d.source_id == c.source_id:
                continue
            if 0 <= (c.date - d.date).days <= ROUND_TRIP_DAYS:
                used.add(d.id)
                hits.add(c.id)
                break
    return hits
