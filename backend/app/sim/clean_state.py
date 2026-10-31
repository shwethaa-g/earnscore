"""Check that the database is in the freshly generated state (python -m app.cli verify-clean).

Read-only: scores are recomputed in memory and nothing is written. The expected values are those of the
deterministic generated dataset (seed 20261030); if the generator or the scoring configuration changes, update
EXPECTED_WORKERS.
"""
from __future__ import annotations

import os
import time
import urllib.request

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Application, Dispute, EarlyWarning, Lender, ShareLink, SimRun, Snapshot, User
from app.scoring import engine
from app.services import model_registry
from app.services.snapshots import build_input, data_end
from app.sim.generate import GEN_DOMAIN, LENDERS, NAMED, email_for

# email prefix: (score, band, confidence, flags that must be present)
EXPECTED_WORKERS = {
    "meena.sundaram": (77, "B", "High", set()),
    "suresh.kumar": (78, "B", "Low", set()),
    "pooja.sharma": (62, "C", "High", set()),
    "deepa.krishnan": (24, "E", "High", set()),
    "vijay.anand": (82, "A", "High", {"round_trip", "unmatched_payout"}),
}
GANESH_LOAN = (85, "A", "modified")  # his loan was decided on data up to August, before a 10-week illness
EXPECTED_APPLICATIONS = 10
EXPECTED_DISPUTES = 1


def wait_healthy(url: str, timeout_s: int = 180) -> None:
    deadline = time.time() + timeout_s
    while True:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status == 200:
                    return
        except OSError:
            pass
        if time.time() > deadline:
            raise SystemExit(f"FAIL  {url} did not answer within {timeout_s}s")
        time.sleep(2)


def check() -> list[tuple[bool, str]]:
    s = get_settings()
    out: list[tuple[bool, str]] = []

    def ok(cond: bool, text: str) -> None:
        out.append((bool(cond), text))

    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.email == s.seed_admin_email.lower()))
        ok(admin and admin.role == "admin" and admin.is_active, f"admin {s.seed_admin_email}")
        officer = db.scalar(select(User).where(User.email == s.seed_officer_email.lower()))
        ok(officer and officer.role == "officer" and officer.lender and officer.lender.name == LENDERS[0]["name"],
           f"officer {s.seed_officer_email} at {LENDERS[0]['name']}")
        names = set(db.scalars(select(Lender.name)).all())
        ok(names == {l["name"] for l in LENDERS}, f"lenders: {', '.join(sorted(names))}")

        named = [email_for(row[0]) for row in NAMED]
        found = db.scalar(select(func.count()).select_from(User).where(User.email.in_(named), User.can_login.is_(True)))
        ok(found == len(named), f"generated workers with a login: {found} of {len(named)}")
        extra = db.scalars(select(User.email).where(User.role == "worker", User.can_login.is_(True),
                                                    User.email.not_in(named + [s.seed_worker_email.lower()]))).all()
        ok(not extra, "no workers registered since the reset" + (f" (found: {', '.join(extra)})" if extra else
                                                                  " (Kumar Velu not yet registered)"))

        mv = model_registry.active(db)
        ok(mv.version == "v1", f"active model {mv.version}")
        for prefix, (score, band, conf, flags) in EXPECTED_WORKERS.items():
            u = db.scalar(select(User).where(User.email == f"{prefix}@{GEN_DOMAIN}"))
            if not u:
                ok(False, f"{prefix}: missing")
                continue
            inp, _ = build_input(db, u, data_end(db, u.id))
            run = engine.run(inp)
            got_score, got_band = model_registry.score(mv, run)
            got_flags = {f["flag"] for f in run["flags"]}
            good = (got_score, got_band, run["confidence"]) == (score, band, conf) and flags <= got_flags
            text = f"{u.name}: {got_score} {got_band}, {run['confidence']} confidence"
            if flags:
                text += f", flags {', '.join(sorted(got_flags))}"
            ok(good, text + ("" if good else f"  (expected {score} {band} {conf})"))

        ganesh = db.scalar(select(User).where(User.email == f"ganesh.pillai@{GEN_DOMAIN}"))
        refreshes = db.scalar(select(func.count()).select_from(Snapshot).where(Snapshot.user_id == ganesh.id,
                                                                               Snapshot.kind == "refresh"))
        warnings = db.scalar(select(func.count()).select_from(EarlyWarning))
        loan = db.scalar(select(Application).where(Application.user_id == ganesh.id))
        got = (loan.snapshot.score, loan.snapshot.band, loan.status) if loan else None
        ok(got == GANESH_LOAN and refreshes == 0 and warnings == 0,
           f"Ganesh Pillai: loan {got[2] if got else 'missing'} at {got[0] if got else '-'} {got[1] if got else ''}, "
           f"{refreshes} monthly refreshes, {warnings} early warnings (before the monthly refresh)")
        apps = db.scalar(select(func.count()).select_from(Application))
        ok(apps == EXPECTED_APPLICATIONS, f"applications: {apps} (generated)")
        disputes = db.scalar(select(func.count()).select_from(Dispute))
        ok(disputes == EXPECTED_DISPUTES, f"disputes: {disputes} (generated)")
        closed = db.scalar(select(func.count()).select_from(ShareLink).where(ShareLink.revoked_at.is_not(None)))
        ok(closed == 0, f"revoked share links: {closed}")
        ok(db.scalar(select(func.count()).select_from(SimRun)) >= 1, "validation run stored")
        db.rollback()
    return out


def main(url: str | None) -> None:
    url = url or f"http://127.0.0.1:{os.environ.get('PORT', '8000')}/healthz"
    wait_healthy(url)
    print(f"OK    health: {url}")
    results = check()
    for good, text in results:
        print(("OK    " if good else "FAIL  ") + text)
    if not all(g for g, _ in results):
        raise SystemExit("Not clean: see FAIL lines above.")
