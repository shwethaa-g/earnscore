from datetime import date

from app.ingest.classify import classify
from app.ingest.reconcile import Credit, Movement, Payout, find_round_trips, is_match, reconcile

D = date(2026, 6, 1)
NARR = "NEFT CR-X-BUNDL TECHNOLOGIES SWIGGY-PAYOUT"


def c(i, days, amt, narr=NARR, platform=""):
    return Credit(i, date.fromordinal(D.toordinal() + days), amt, narr, platform)


def test_one_percent_tolerance_boundary():
    p = Payout(1, D, 1000.0, "Swiggy")
    assert is_match(p, c(10, 1, 1010.0))      # exactly 1%
    assert is_match(p, c(10, 1, 990.0))
    assert not is_match(p, c(10, 1, 1010.5))  # just over 1%


def test_zero_to_three_day_window():
    p = Payout(1, D, 1000.0, "Swiggy")
    assert is_match(p, c(10, 0, 1000.0))
    assert is_match(p, c(10, 3, 1000.0))
    assert not is_match(p, c(10, 4, 1000.0))
    assert not is_match(p, c(10, -1, 1000.0))  # credit before the payout


def test_payer_must_match_platform():
    p = Payout(1, D, 1000.0, "Zomato")
    assert not is_match(p, c(10, 1, 1000.0))
    assert is_match(p, c(10, 1, 1000.0, "UPI/CR/1/ZOMATO LTD"))


def test_duplicates_match_one_to_one():
    payouts = [Payout(1, D, 1000.0, "Swiggy")]
    credits = [c(10, 1, 1000.0), c(11, 1, 1000.0)]
    matches, unmatched = reconcile(payouts, credits)
    assert matches == [(1, 10)] and unmatched == []
    # two identical payouts and one credit: one is matched, the other is flagged unmatched
    matches, unmatched = reconcile([Payout(1, D, 1000.0, "Swiggy"), Payout(2, D, 1000.0, "Swiggy")], [c(10, 1, 1000.0)])
    assert len(matches) == 1 and len(unmatched) == 1


def test_closest_lag_preferred():
    matches, _ = reconcile([Payout(1, D, 1000.0, "Swiggy")], [c(10, 3, 1000.0), c(11, 1, 1004.0)])
    assert matches == [(1, 11)]


def test_classification_rules():
    assert classify("IMPS/SELF/OWN A/C XX1234", "credit").kind == "self_transfer"
    assert classify("UPI/CR/1/RAVI TRANSFER", "credit", own_refs=["XXXX1234"]).kind == "earned"
    assert classify("NEFT TRF FROM A/C 1234", "credit", own_refs=["XXXX1234"]).kind == "self_transfer"
    assert classify("REFUND/ONLINE ORDER/88", "credit").kind == "refund"
    assert classify("LOAN DISB/GRAMA FINANCE", "credit").kind == "loan"
    t = classify(NARR, "credit")
    assert t.kind == "earned" and t.platform == "Swiggy"
    assert classify("NACH RTN CHG/X/INSUFFICIENT FUNDS", "debit").category == "bounce"
    assert classify("BBPS/BESCOM/ELECTRICITY BILL", "debit").category == "utilities"
    assert classify("UPI/DR/1/HPCL FUEL STATION", "debit").category == "fuel"
    assert classify("SB INT.PD", "credit").kind == "other"


def test_round_trip_detection_needs_another_own_account():
    moves = [Movement(1, 100, D, 5000.0, "debit"), Movement(2, 200, date(2026, 6, 2), 5000.0, "credit"),
             Movement(3, 200, D, 700.0, "debit"), Movement(4, 200, D, 700.0, "credit")]
    assert find_round_trips(moves) == {2}
