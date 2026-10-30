"""Deterministic classification rules for bank transactions (BUILD.md section 5.2).

Rules always run offline. An optional language model may re-tag only rows these rules leave as
`other / unclassified`; see app/services/language.py.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Payer identifiers seen in bank narrations for each platform. Labels only: no data comes from these companies.
PLATFORM_PAYERS: dict[str, list[str]] = {
    "Swiggy": ["SWIGGY", "BUNDL TECH"],
    "Zomato": ["ZOMATO"],
    "Uber": ["UBER INDIA", "UBER"],
    "Rapido": ["RAPIDO", "ROPPEN"],
    "Urban Company": ["URBANCLAP", "URBAN COMPANY", "URBANCOMPANY"],
}
PLATFORMS = list(PLATFORM_PAYERS)

LOAN = ["LOAN DISB", "DISBURSAL", "DISBURSEMENT", "LOAN CR", "PERSONAL LOAN CR", "LOAN AMOUNT CR"]
REFUND = ["REFUND", "REVERSAL", "RFND", "CASHBACK", "REV-", "CHARGEBACK"]
SELF = ["SELF", "OWN A/C", "OWN ACCOUNT", "OWN AC", "TO SELF", "FROM SELF"]
INTEREST = ["INT.PD", "INT PD", "INTEREST", "SB INT", "INT CREDIT"]
CASH_DEP = ["CASH DEP", "CASH DEPOSIT", "BY CASH", "CDM"]
FOREIGN = ["INWARD REMIT", "FOREIGN", "FIRC", "SWIFT", "PAYPAL", "WISE ", "PAYONEER", "USD", "EUR", "GBP"]
BOUNCE = ["NACH RTN", "ECS RTN", "RETURN CHG", "RTN CHG", "BOUNCE", "INSUFFICIENT", "NACH RETURN", "ECS RETURN", "DISHONOUR"]
EMI = ["EMI", "NACH DR", "ECS DR", "LOAN REPAY", "LOAN EMI", "ACH DR"]
RENT = ["RENT"]
UTILITIES = ["ELECTRICITY", "TNEB", "TANGEDCO", "BESCOM", "MSEDCL", "TSSPDCL", "BSES", "TATA POWER", "WATER", "BROADBAND",
             "AIRTEL", "JIO", "RECHARGE", "INDANE", "HP GAS", "BHARAT GAS", "BBPS", "BILLPAY", "ACT FIBERNET", "VI POSTPAID"]
FUEL = ["PETROL", "FUEL", "HPCL", "BPCL", "IOCL", "INDIAN OIL", "SHELL", "DIESEL", "CNG"]
SAVINGS = ["RECURRING DEP", "RD INST", "RD-", "SIP", "MUTUAL FUND", "PPF", "SAVINGS TRF", "GOLD SAVINGS"]
CREDIT_CHANNELS = ["UPI/CR", "UPI-CR", "UPI CR", "NEFT CR", "NEFT-", "IMPS CR", "IMPS-", "IMPS/", "RTGS", "NEFT/", "BY TRANSFER"]

ESSENTIAL_CATEGORIES = ("rent", "utilities", "fuel", "emi")


@dataclass
class Tag:
    kind: str  # earned | self_transfer | refund | loan | expense | other
    category: str
    platform: str = ""
    rule: str = ""
    payer: str = ""


def _has(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def platform_of(narration: str) -> str:
    t = narration.upper()
    for name, ids in PLATFORM_PAYERS.items():
        if _has(t, ids):
            return name
    return ""


def payer_of(narration: str) -> str:
    """Best-effort counterparty name from common Indian bank narration formats."""
    t = narration.upper()
    m = re.match(r"UPI[/-](?:CR|DR)[/-][^/]*[/-]([^/@]+)", t)
    if m:
        return m.group(1).strip()[:40]
    m = re.match(r"(?:NEFT|IMPS|RTGS)[/ -](?:CR[/ -])?[^/ -]*[/ -]([^/]+)", t)
    if m:
        return m.group(1).strip()[:40]
    return re.sub(r"[^A-Z ]", " ", t).split("  ")[0].strip()[:40]


def _mentions_own(t: str, own_refs: list[str], own_name: str) -> bool:
    for ref in own_refs:
        tail = re.sub(r"\D", "", ref)[-4:]
        if tail and (f"X{tail}" in t or f"XX{tail}" in t or f"*{tail}" in t or f"A/C {tail}" in t or t.endswith(tail)):
            return True
    if own_name:
        name = own_name.upper()
        if name in t and ("TRF" in t or "TRANSFER" in t or "IMPS" in t or "NEFT" in t):
            return True
    return False


def classify(narration: str, direction: str, own_refs: list[str] | None = None, own_name: str = "") -> Tag:
    t = (narration or "").upper()
    own_refs = own_refs or []
    if direction == "credit":
        if _has(t, LOAN):
            return Tag("loan", "loan_credit", rule="loan_keyword")
        if _has(t, REFUND):
            return Tag("refund", "refund", rule="refund_keyword")
        if _has(t, SELF) or _mentions_own(t, own_refs, own_name):
            return Tag("self_transfer", "self_transfer", rule="own_account")
        p = platform_of(t)
        if p:
            return Tag("earned", "payout", platform=p, rule="platform_payer", payer=p)
        if _has(t, INTEREST):
            return Tag("other", "interest", rule="interest_keyword")
        if _has(t, CASH_DEP):
            return Tag("other", "cash_deposit", rule="cash_deposit")
        if _has(t, FOREIGN):
            return Tag("earned", "client_payment_fx", rule="foreign_remittance", payer=payer_of(t))
        if _has(t, CREDIT_CHANNELS):
            return Tag("earned", "customer_payment", rule="digital_credit", payer=payer_of(t))
        return Tag("other", "unclassified", rule="no_rule")
    # debits
    if _has(t, BOUNCE):
        return Tag("expense", "bounce", rule="bounce_keyword")
    if _has(t, SELF) or _mentions_own(t, own_refs, own_name):
        return Tag("self_transfer", "self_transfer", rule="own_account")
    if _has(t, SAVINGS):
        return Tag("other", "savings", rule="savings_keyword")
    if _has(t, EMI):
        return Tag("expense", "emi", rule="emi_keyword")
    if _has(t, RENT):
        return Tag("expense", "rent", rule="rent_keyword")
    if _has(t, UTILITIES):
        return Tag("expense", "utilities", rule="utility_keyword")
    if _has(t, FUEL):
        return Tag("expense", "fuel", rule="fuel_keyword")
    return Tag("expense", "general", rule="default_debit")
