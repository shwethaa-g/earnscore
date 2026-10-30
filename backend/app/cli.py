"""Command line: python -m app.cli <command>

  migrate    apply Alembic migrations
  seed       create/update the three role accounts from env vars and set generated workers' password
  generate   generate the named worker accounts + cohort population through the upload pipeline
  simulate   run the validation simulator (>= 5,000 workers), train/register EBM v2, store in sim_runs
  purge      withdraw expired consents and delete data whose scheduled deletion time has passed
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import PASSWORD_RULE, hash_password, password_ok

log = logging.getLogger("earnscore.cli")


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    from app.core.config import BACKEND_DIR

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


def _upsert(db, email: str, password: str, name: str, role: str, lender_id: int | None = None):
    from app.models import User, WorkerProfile

    if not password_ok(password):
        raise SystemExit(f"Password for {email} does not meet the rule: {PASSWORD_RULE}")
    u = db.scalar(select(User).where(User.email == email.lower()))
    if not u:
        u = User(email=email.lower(), name=name, role=role)
        if role == "worker":
            u.profile = WorkerProfile(city="Chennai", work_type="rider", languages=["ta", "en"])
        db.add(u)
    u.password_hash = hash_password(password)
    u.role, u.lender_id, u.can_login, u.is_active = role, lender_id, True, True
    return u


def seed() -> None:
    from app.models import Lender, User
    from app.services import model_registry
    from app.sim.generate import GEN_DOMAIN, NAMED, email_for, ensure_lenders

    s = get_settings()
    missing = [k for k in ("seed_admin_email", "seed_admin_password", "seed_officer_email", "seed_officer_password",
                           "seed_worker_email", "seed_worker_password") if not getattr(s, k)]
    if missing:
        raise SystemExit("Set these environment variables first: " + ", ".join(m.upper() for m in missing))
    with SessionLocal() as db:
        model_registry.ensure_v1(db)
        lenders = ensure_lenders(db)
        _upsert(db, s.seed_admin_email, s.seed_admin_password, "Audit Admin", "admin")
        _upsert(db, s.seed_officer_email, s.seed_officer_password, "Credit Officer", "officer", lenders[0].id)
        _upsert(db, s.seed_worker_email, s.seed_worker_password, "New Worker", "worker")
        hashed = hash_password(s.seed_worker_password)
        n = 0
        for row in NAMED:
            u = db.scalar(select(User).where(User.email == email_for(row[0])))
            if u:
                u.password_hash = hashed
                n += 1
        db.commit()
        print(f"seeded: admin={s.seed_admin_email} officer={s.seed_officer_email} worker={s.seed_worker_email} "
              f"generated workers with password: {n} (emails *@{GEN_DOMAIN})")
        print("lenders:", ", ".join(l.name for l in db.scalars(select(Lender)).all()))


def checkpoint() -> None:
    """Fold the SQLite write-ahead log back into the database file after bulk writes."""
    if get_settings().database_url.startswith("sqlite"):
        from sqlalchemy import text

        with SessionLocal() as db:
            db.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))


def generate(cohort_size: int) -> None:
    from app.sim.generate import generate as gen

    s = get_settings()
    out = s.data_dir / "generated_statements"
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with SessionLocal() as db:
        stats = gen(db, out, cohort_size=cohort_size)
    checkpoint()
    print(f"generated {stats} in {time.time() - t0:.0f}s; statement files in {out}")


def simulate(n: int) -> None:
    from app.sim.simulate import run

    with SessionLocal() as db:
        r = run(db, n_workers=n)
        print(f"sim_run {r.id}: {r.metrics}")
    checkpoint()


def purge() -> None:
    from app.services.consent import purge_due

    with SessionLocal() as db:
        print(purge_due(db))


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("seed")
    g = sub.add_parser("generate")
    g.add_argument("--cohort-size", type=int, default=21)
    sm = sub.add_parser("simulate")
    sm.add_argument("--workers", type=int, default=5000)
    sub.add_parser("purge")
    a = ap.parse_args(argv)
    if a.cmd == "migrate":
        migrate()
    elif a.cmd == "seed":
        seed()
    elif a.cmd == "generate":
        generate(a.cohort_size)
    elif a.cmd == "simulate":
        simulate(a.workers)
    elif a.cmd == "purge":
        purge()


if __name__ == "__main__":
    main(sys.argv[1:])
