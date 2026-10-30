"""Deterministic model of a gig worker's financial life (DATA_SOURCES.md section 3).

Produces day-level bank transactions per account and platform payout rows. Everything here is generated:
names, accounts and amounts are fictional. Platform names are labels only.

Used by:
  * sim/generate.py  - writes these rows as bank/platform statements and ingests them via the upload pipeline
  * sim/simulate.py  - the validation simulator, which also continues the life past the scoring date to
                       simulate repayment of a loan (default = cash cannot cover the EMI 3 cycles in a row)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

END_DATE = date(2026, 10, 25)  # last day of generated history (a Sunday)

CITIES = ["Chennai", "Coimbatore", "Madurai", "Bengaluru", "Hyderabad", "Mumbai", "Delhi"]
WORK_TYPES = ["rider", "home_service", "freelancer", "vendor"]
TN_CITIES = {"Chennai", "Coimbatore", "Madurai"}

MONSOON = {  # months with the dominant monsoon in each city
    "Mumbai": {6, 7, 8, 9}, "Bengaluru": {6, 7, 8, 9, 10}, "Hyderabad": {7, 8, 9}, "Delhi": {7, 8, 9},
    "Chennai": {10, 11, 12}, "Coimbatore": {10, 11}, "Madurai": {10, 11, 12},
}
DIWALI = [date(2024, 10, 31), date(2025, 10, 20), date(2026, 11, 8)]
EID = [date(2024, 4, 10), date(2025, 3, 31), date(2026, 3, 20)]
PONGAL = [date(2025, 1, 14), date(2026, 1, 14), date(2024, 1, 15)]

EFFECTS = {  # multiplicative effects by work type
    "rider": {"monsoon": 0.18, "feb_dip": -0.15, "diwali": 0.20, "pongal": -0.08, "eid": 0.10, "dec_dip": 0.0},
    "home_service": {"monsoon": -0.15, "feb_dip": -0.05, "diwali": 0.35, "pongal": 0.10, "eid": 0.05, "dec_dip": 0.0},
    "freelancer": {"monsoon": 0.0, "feb_dip": -0.05, "diwali": -0.10, "pongal": 0.0, "eid": 0.0, "dec_dip": -0.30},
    "vendor": {"monsoon": -0.20, "feb_dip": -0.08, "diwali": 0.40, "pongal": 0.30, "eid": 0.25, "dec_dip": 0.0},
}
BASE_WEEKLY = {"rider": 5200, "home_service": 5800, "freelancer": 8500, "vendor": 4800}
CITY_LEVEL = {"Mumbai": 1.15, "Bengaluru": 1.15, "Delhi": 1.1, "Hyderabad": 1.05, "Chennai": 1.0, "Coimbatore": 0.9, "Madurai": 0.85}
RIDER_PAIRS = [("Swiggy", "Zomato"), ("Uber", "Rapido"), ("Swiggy", "Rapido"), ("Zomato", "Uber")]
PAYOUT_WEEKDAY = {"Swiggy": 2, "Zomato": 0, "Uber": 1, "Rapido": 3, "Urban Company": 0}
POWER = {"Chennai": "TANGEDCO", "Coimbatore": "TANGEDCO", "Madurai": "TANGEDCO", "Bengaluru": "BESCOM",
         "Hyderabad": "TSSPDCL", "Mumbai": "MSEDCL", "Delhi": "BSES RAJDHANI"}
MERCHANTS = ["KUMAR STORES", "SRI BALAJI MART", "ANNAPOORNA MESS", "CITY MEDICALS", "FRESH VEG CORNER", "RAJ TEA STALL",
             "NEW LAKSHMI TEXTILES", "STAR MOBILES", "GREEN LEAF HOTEL", "MAHALAKSHMI BAKERY", "DAILY NEEDS STORE"]
CUSTOMERS = ["ARUN P", "DIVYA S", "KARTHIK R", "MEENA K", "SURESH V", "PRIYA N", "RAHUL M", "ANITHA J", "FAROOQ A",
             "GEETHA L", "MOHAN B", "SANA Q", "VIKRAM T", "LATHA D", "IMRAN H", "POOJA G", "RAVI C", "NISHA F"]
CLIENTS = ["NILAMBUR DESIGN WORKS LLP", "BLUE KITE MEDIA", "ORBITAL APPS PVT LTD", "PAPERBOAT STUDIO", "KAVERI EXPORTS"]
FX_CLIENTS = ["NORTHWIND LABS USD", "LUMEN CREATIVE GBP", "HARBOR DIGITAL EUR"]
LENDERS_EXISTING = ["TWOWHEEL FINSERV", "PHONE EASY CREDIT", "GRAMA FINANCE"]
LANDLORDS = ["S RAMESH", "M VASANTHI", "K ABDUL", "P NAIR", "R GUPTA", "L DSOUZA"]


@dataclass
class Txn:
    date: date
    account: int
    narration: str
    direction: str
    amount: float
    category: str = ""     # ground truth for the simulator: earned | rent | utilities | fuel | emi | bounce | savings | self | spend | refund | loan | other
    platform: str = ""
    balance: float = 0.0
    ref: str = ""


@dataclass
class PayoutRow:
    date: date
    platform: str
    amount: float
    trips: int
    hours: float
    ref: str
    account: int


@dataclass
class Persona:
    idx: int
    name: str
    city: str
    work_type: str
    weeks: int
    accounts: int
    reliability: float
    discipline: float
    base_weekly: float
    base_hours: float
    platforms: list[str]
    second_platform_account: int
    has_emi: bool
    emi_amount: float
    rent: float
    saves: bool
    group: str
    flags: set[str] = field(default_factory=set)  # scenario switches: round_trip, large_recent_credit, missing_account


@dataclass
class Life:
    persona: Persona
    start: date
    end: date
    txns: list[Txn]
    payouts: list[PayoutRow]
    weekly_income: dict[date, float]
    weekly_hours: dict[date, float]
    cash_end: float = 0.0
    outcome: dict | None = None


def season(city: str, wt: str, d: date) -> float:
    e = EFFECTS[wt]
    f = 1.0
    if d.month in MONSOON[city]:
        f += e["monsoon"]
    woy = d.isocalendar()[1]
    if 6 <= woy <= 9:
        f += e["feb_dip"]
    if woy >= 51:
        f += e["dec_dip"]
    if any(0 <= (dw - d).days <= 10 for dw in DIWALI):
        f += e["diwali"]
    if city in TN_CITIES and any(abs((p - d).days) <= 3 for p in PONGAL):
        f += e["pongal"]
    if city in {"Hyderabad", "Mumbai", "Delhi"} and any(0 <= (x - d).days <= 7 for x in EID):
        f += e["eid"]
    return max(f, 0.2)


def make_persona(rng: np.random.Generator, idx: int, name: str, city: str, wt: str, weeks: int, accounts: int,
                 group: str = "", flags: set[str] | None = None) -> Persona:
    rel = float(rng.beta(5, 2))
    disc = float(rng.beta(4, 2.5))
    base = BASE_WEEKLY[wt] * CITY_LEVEL[city] * float(rng.lognormal(0, 0.25))
    if wt == "rider":
        plats = list(RIDER_PAIRS[int(rng.integers(len(RIDER_PAIRS)))])
    elif wt == "home_service":
        plats = ["Urban Company"]
    else:
        plats = []
    hours = float(np.clip(rng.normal(46, 8), 25, 72))
    return Persona(idx=idx, name=name, city=city, work_type=wt, weeks=weeks, accounts=accounts, reliability=rel,
                   discipline=disc, base_weekly=base, base_hours=hours, platforms=plats,
                   second_platform_account=1 if (accounts > 1 and rng.random() < 0.5) else 0,
                   has_emi=bool(rng.random() < 0.45), emi_amount=float(round(rng.uniform(1200, 3500), -1)),
                   rent=float(round(base * 4.3 * rng.uniform(0.12, 0.24), -2)), saves=bool(disc > 0.6 and rng.random() < 0.8),
                   group=group or ("woman" if rng.random() < (0.45 if wt == "home_service" else 0.25) else "man"),
                   flags=flags or set())


class _Book:
    def __init__(self, n_accounts: int, opening: float):
        self.bal = [opening] + [opening * 0.3] * (n_accounts - 1)
        self.txns: list[Txn] = []
        self.counter = 0

    def ref(self) -> str:
        self.counter += 1
        return f"{604000000000 + self.counter * 7919 % 99999999:012d}"

    def credit(self, d, acct, narr, amt, cat, platform=""):
        amt = round(amt, 2)
        self.bal[acct] = round(self.bal[acct] + amt, 2)
        self.txns.append(Txn(d, acct, narr, "credit", amt, cat, platform, self.bal[acct], self.ref()))

    def debit(self, d, acct, narr, amt, cat, force=False) -> bool:
        amt = round(amt, 2)
        if not force and self.bal[acct] < amt:
            return False
        self.bal[acct] = round(self.bal[acct] - amt, 2)
        self.txns.append(Txn(d, acct, narr, "debit", amt, cat, "", self.bal[acct], self.ref()))
        return True


def live(p: Persona, seed: int, extra_weeks: int = 0, loan_emi: float = 0.0) -> Life:
    """Simulate p.weeks of history ending END_DATE, then optionally extra_weeks with a new weekly loan EMI."""
    rng = np.random.default_rng(seed)
    total_weeks = p.weeks + extra_weeks
    start = END_DATE - timedelta(days=p.weeks * 7 - 1)
    book = _Book(p.accounts, p.base_weekly * (0.4 + 2.5 * p.discipline))
    payouts: list[PayoutRow] = []
    weekly_income: dict[date, float] = {}
    weekly_hours: dict[date, float] = {}
    last4 = [f"{(p.idx * 37 + a * 1013) % 10000:04d}" for a in range(p.accounts)]
    first_name = p.name.split()[0].upper()

    # shocks
    shock = {}
    years = total_weeks / 52
    for kind, prob, dur in (("deactivation", 0.15, (2, 5)), ("illness", 0.3, (1, 4)), ("breakdown", 0.35, (1, 2))):
        for _ in range(int(rng.poisson(prob * years * (1.4 - p.reliability)))):
            w0 = int(rng.integers(0, total_weeks))
            for w in range(w0, min(total_weeks, w0 + int(rng.integers(*dur)))):
                shock[w] = kind
    if "recent_shock" in p.flags:
        for w in range(p.weeks - 10, p.weeks):  # scenario: a 10-week illness ending at the data end
            shock[w] = "illness"

    pending_payout: dict[tuple[str, date], tuple[float, int, float]] = {}
    emi_misses = 0
    defaulted_at = None
    loan_paid = 0
    cash_start_outcome = None
    for w in range(total_weeks):
        monday = start + timedelta(days=7 * w)
        in_outcome = w >= p.weeks
        if in_outcome and cash_start_outcome is None:
            cash_start_outcome = sum(book.bal)
        s = season(p.city, p.work_type, monday + timedelta(days=3))
        active = rng.random() < (0.72 + 0.27 * p.reliability)
        mult = s * float(rng.lognormal(0, 0.10 + 0.25 * (1 - p.reliability)))
        k = shock.get(w)
        if k == "illness":
            mult *= 0.3
        elif k == "breakdown":
            mult *= 0.5
        if not active:
            mult *= 0.0
        income = p.base_weekly * mult
        hours = p.base_hours * (mult ** 0.5) if mult > 0 else 0.0
        weekly_income[monday] = 0.0
        weekly_hours[monday] = round(hours, 1) if p.platforms else 0.0
        if k == "breakdown" and p.work_type in {"rider", "home_service"}:
            book.debit(monday + timedelta(days=1), 0, f"UPI/DR/{book.ref()[:6]}/SRI MURUGAN AUTO WORKS", rng.uniform(2500, 9000), "spend", force=True)

        # ---- income
        if p.work_type == "rider":
            shares = [0.6, 0.4]
            for pi, plat in enumerate(p.platforms):
                amt = income * shares[pi]
                if k == "deactivation" and pi == 0:
                    amt = 0.0
                if amt > 0:
                    trips = int(max(1, amt / rng.uniform(55, 75)))
                    pending_payout[(plat, monday)] = (amt, trips, hours * shares[pi])
        elif p.work_type == "home_service":
            jobs = int(rng.poisson(max(0.1, 6 * mult)))
            uc = sum(rng.uniform(450, 1400) for _ in range(jobs)) * 0.75
            if uc > 0:
                pending_payout[("Urban Company", monday)] = (uc, jobs, hours * 0.75)
            for _ in range(int(rng.poisson(1.5 * mult))):
                d = monday + timedelta(days=int(rng.integers(0, 7)))
                amt = rng.uniform(300, 1200)
                book.credit(d, 0, f"UPI/CR/{book.ref()[:9]}/{CUSTOMERS[int(rng.integers(len(CUSTOMERS)))]}/PAYMENT", amt, "earned")
                weekly_income[monday] += amt
        elif p.work_type == "freelancer":
            n_pay = int(rng.poisson(0.8 * min(mult, 2.5)))
            for _ in range(n_pay):
                d = monday + timedelta(days=int(rng.integers(0, 5)))
                amt = income / max(n_pay, 1) * rng.uniform(0.6, 1.4) * 1.25
                if rng.random() < 0.3:
                    book.credit(d, 0, f"INWARD REMITTANCE/{book.ref()[:8]}/{FX_CLIENTS[int(rng.integers(len(FX_CLIENTS)))]}", amt, "earned")
                else:
                    book.credit(d, 0, f"NEFT CR-{book.ref()[:8]}-{CLIENTS[int(rng.integers(len(CLIENTS)))]}", amt, "earned")
                weekly_income[monday] += amt
        else:  # vendor: daily UPI collections, six days a week
            for day in range(6):
                d = monday + timedelta(days=day)
                daily = income / 6 * rng.uniform(0.7, 1.3)
                if daily <= 0:
                    continue
                n = int(rng.integers(2, 5))
                parts = rng.dirichlet(np.ones(n)) * daily
                for part in parts:
                    acct = 1 if (p.accounts > 1 and rng.random() < 0.3) else 0
                    book.credit(d, acct, f"UPI/CR/{book.ref()[:9]}/{CUSTOMERS[int(rng.integers(len(CUSTOMERS)))]}/UPI", part, "earned")
                    weekly_income[monday] += part
            if rng.random() < 0.5:
                book.credit(monday + timedelta(days=5), 0, "CASH DEPOSIT BY SELF CDM", rng.uniform(500, 2000), "other")

        # platform payouts for last week's work arrive this week; bank credit 0-2 days later
        for (plat, wk), (amt, trips, hrs) in list(pending_payout.items()):
            if wk == monday:
                continue
            pd_ = monday + timedelta(days=PAYOUT_WEEKDAY[plat])
            ref = f"{plat[:3].upper()}{p.idx:04d}{w:03d}"
            acct = p.second_platform_account if (len(p.platforms) > 1 and plat == p.platforms[1]) else 0
            if not in_outcome:
                payouts.append(PayoutRow(pd_, plat, round(amt, 2), trips, round(hrs, 1), ref, acct))
            lag = int(rng.choice([0, 1, 1, 1, 2]))
            r = rng.random()
            bank_amt = amt if r < 0.95 else (amt * (1 + rng.uniform(-0.003, 0.003)) if r < 0.99 else amt * 0.97)
            payer = {"Swiggy": "BUNDL TECHNOLOGIES SWIGGY", "Zomato": "ZOMATO LTD", "Uber": "UBER INDIA SYSTEMS",
                     "Rapido": "ROPPEN TRANSPORTATION RAPIDO", "Urban Company": "URBANCLAP TECHNOLOGIES"}[plat]
            book.credit(pd_ + timedelta(days=lag), acct, f"NEFT CR-{ref}-{payer}-PAYOUT", bank_amt, "earned", plat)
            weekly_income[monday] += bank_amt
            del pending_payout[(plat, wk)]

        # ---- expenses
        week_income = weekly_income[monday]
        ess_week = p.rent / 4.3 + (p.emi_amount / 4.3 if p.has_emi else 0)
        for day in range(7):
            d = monday + timedelta(days=day)
            if d.day == 5:
                late = rng.random() < 0.45 * (1 - p.discipline)
                pay_day = d + timedelta(days=int(rng.integers(7, 15))) if late else d - timedelta(days=int(rng.integers(0, 3)))
                book.debit(pay_day, 0, f"UPI/DR/{book.ref()[:9]}/{LANDLORDS[p.idx % len(LANDLORDS)]}/RENT", p.rent, "rent", force=True)
                if p.has_emi:
                    if book.bal[0] >= p.emi_amount:
                        book.debit(d, 0, f"NACH DR/{LENDERS_EXISTING[p.idx % 3]}/EMI {p.idx:05d}", p.emi_amount, "emi")
                    else:
                        book.debit(d, 0, f"NACH RTN CHG/{LENDERS_EXISTING[p.idx % 3]}/INSUFFICIENT FUNDS", 590.0, "bounce", force=True)
                if p.saves:
                    book.debit(d + timedelta(days=1), 0, "RD INSTALMENT TRF", round(p.base_weekly * 0.3, -1), "savings")
            if d.day == 10:
                book.debit(d + timedelta(days=0 if rng.random() < 0.5 + 0.5 * p.discipline else int(rng.integers(6, 12))), 0,
                           f"BBPS/{POWER[p.city]}/ELECTRICITY BILL", rng.uniform(450, 1400), "utilities", force=True)
            if d.day == 15:
                book.debit(d, 0, "BBPS/JIO PREPAID RECHARGE", 299.0, "utilities", force=True)
            if d.day == 20 and p.accounts > 1:
                amt = round(rng.uniform(1000, 4000), -2)
                if book.debit(d, 0, f"IMPS/SELF/OWN A/C XX{last4[1]}", amt, "self"):
                    book.credit(d, 1, f"IMPS/SELF/OWN A/C XX{last4[0]}", amt, "self")
            if d.day == 22 and p.accounts > 2:
                amt = round(rng.uniform(800, 2500), -2)
                if book.debit(d, 0, f"IMPS/SELF/OWN A/C XX{last4[2]}", amt, "self"):
                    book.credit(d, 2, f"IMPS/SELF/OWN A/C XX{last4[0]}", amt, "self")
            if d.day == 25 and p.accounts > 1 and book.bal[1] > 1500:
                amt = round(book.bal[1] * 0.6, -2)
                if amt > 0 and book.debit(d, 1, f"UPI/DR/{book.ref()[:9]}/{first_name} SELF TRANSFER", amt, "self"):
                    book.credit(d, 0, f"UPI/CR/{book.ref()[:9]}/{first_name} SELF TRANSFER", amt, "self")
        if p.work_type in {"rider", "home_service"} and week_income > 0:
            for _ in range(3 if p.work_type == "rider" else 1):
                book.debit(monday + timedelta(days=int(rng.integers(0, 7))), 0, f"UPI/DR/{book.ref()[:9]}/HPCL FUEL STATION",
                           rng.uniform(150, 400), "fuel", force=True)
        if in_outcome and loan_emi > 0:
            loan_day = monday + timedelta(days=4)
            if sum(book.bal) >= loan_emi:
                take = loan_emi
                for a in range(p.accounts):
                    t = min(take, max(book.bal[a], 0))
                    if t > 0:
                        book.debit(loan_day, a, "NACH DR/NEW LOAN EMI", t, "emi")
                        take -= t
                emi_misses = 0
                loan_paid += 1
            else:
                emi_misses += 1
                if emi_misses >= 3 and defaulted_at is None:
                    defaulted_at = w - p.weeks
        # discretionary spending adapts to what is left after essentials (and the new EMI)
        save_rate = 0.04 + 0.22 * p.discipline
        budget = max(0.0, week_income - ess_week - (loan_emi if in_outcome else 0)) * (1 - save_rate)
        if sum(book.bal) < p.base_weekly * 0.5:
            budget *= 0.6
        n = int(rng.integers(3, 7))
        for part in rng.dirichlet(np.ones(n)) * budget:
            book.debit(monday + timedelta(days=int(rng.integers(0, 7))), 0,
                       f"UPI/DR/{book.ref()[:9]}/{MERCHANTS[int(rng.integers(len(MERCHANTS)))]}", part, "spend")
        if rng.random() < 0.08:
            book.credit(monday + timedelta(days=int(rng.integers(0, 7))), 0, f"REFUND/ONLINE ORDER/{book.ref()[:8]}",
                        rng.uniform(150, 1500), "refund")
        if w % 13 == 12:
            book.credit(monday + timedelta(days=6), 0, "SB INT.PD", round(max(book.bal[0], 0) * 0.007, 2), "other")
        if w == p.weeks // 2 and p.idx % 10 == 3:
            book.credit(monday + timedelta(days=2), 0, f"LOAN DISB/{LENDERS_EXISTING[(p.idx + 1) % 3]}/PERSONAL LOAN",
                        round(rng.uniform(15000, 40000), -3), "loan")

    # scenario switches (named accounts only)
    if "round_trip" in p.flags and p.accounts > 1:
        for j in range(4):
            d = END_DATE - timedelta(days=60 - j * 14)
            amt = round(p.base_weekly * 0.8, -2)
            book.debit(d, 1, f"UPI/DR/{book.ref()[:9]}/98{p.idx:04d}0000@okaxis", amt, "self", force=True)
            book.credit(d + timedelta(days=1), 0, f"UPI/CR/{book.ref()[:9]}/{CUSTOMERS[j]}/PAYMENT", amt, "self")
    if "large_recent_credit" in p.flags:
        book.credit(END_DATE - timedelta(days=6), 0, f"IMPS CR/{book.ref()[:8]}/K SUNDARAM", round(p.base_weekly * 5, -3), "other")

    txns = sorted((t for t in book.txns if t.date <= END_DATE + timedelta(days=7 * extra_weeks)), key=lambda t: (t.date, t.account, t.ref))
    # recompute running balances in date order per account (late rent rows were appended out of order)
    opening = {a: (p.base_weekly * (0.4 + 2.5 * p.discipline) if a == 0 else p.base_weekly * (0.4 + 2.5 * p.discipline) * 0.3)
               for a in range(p.accounts)}
    bal = dict(opening)
    for t in txns:
        bal[t.account] = round(bal[t.account] + (t.amount if t.direction == "credit" else -t.amount), 2)
        t.balance = bal[t.account]
    life = Life(p, start, END_DATE, txns, payouts, weekly_income, weekly_hours, cash_end=sum(bal.values()))
    if extra_weeks:
        life.outcome = {"defaulted": defaulted_at is not None, "default_week": defaulted_at, "paid_cycles": loan_paid,
                        "emi": loan_emi}
    return life
