"""Account Aggregator provider interface.

Only regulated entities can be Financial Information Users (FIUs), so EarnScore acts as the lender's
technology provider: the lender raises the consent request and the worker approves it in their AA app.
No AA credentials are configured for this deployment, so `get_provider()` returns the unavailable
provider and the statement-upload path is used. A Setu implementation plugs in behind this interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass
class AATransaction:
    date: date
    narration: str
    direction: str
    amount: float
    balance: float | None
    ref: str


class AAProvider(ABC):
    name: str = "base"

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def create_consent_request(self, worker_ref: str, fi_from: date, fi_to: date) -> dict:
        """Return {'consent_handle': ..., 'redirect_url': ...} for the worker to approve in their AA app."""

    @abstractmethod
    def fetch_transactions(self, consent_handle: str) -> list[AATransaction]: ...


class UnavailableAAProvider(AAProvider):
    name = "none"

    def available(self) -> bool:
        return False

    def create_consent_request(self, worker_ref: str, fi_from: date, fi_to: date) -> dict:
        raise RuntimeError("Account Aggregator is not configured for this lender.")

    def fetch_transactions(self, consent_handle: str) -> list[AATransaction]:
        raise RuntimeError("Account Aggregator is not configured for this lender.")


def get_provider() -> AAProvider:
    return UnavailableAAProvider()


def status() -> dict:
    p = get_provider()
    return {"available": p.available(), "provider": p.name,
            "message": "Bank connection through the Account Aggregator network is opened by a regulated lender. "
                       "Until your lender enables it, upload your bank statement instead (CSV, Excel or PDF)."}
