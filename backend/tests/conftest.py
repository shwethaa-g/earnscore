import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="earnscore-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["DATA_DIR"] = str(_TMP)
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"
os.environ["LLM_PROVIDER"] = "none"
os.environ["ALLOWED_ORIGIN"] = "http://testserver"

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.core.security import auth_limiter, hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Lender, User  # noqa: E402
from app.services import model_registry  # noqa: E402

PASSWORD = "Strongpass123"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        model_registry.ensure_v1(db)
        lender = Lender(name="Test Lender Co-op", alpha=0.5, annual_rate=0.24)
        other = Lender(name="Other Lender", alpha=0.5, annual_rate=0.24)
        db.add_all([lender, other])
        db.flush()
        db.add_all([
            User(email="officer@example.com", name="Officer One", role="officer", lender_id=lender.id, password_hash=hash_password(PASSWORD)),
            User(email="officer2@example.com", name="Officer Two", role="officer", lender_id=other.id, password_hash=hash_password(PASSWORD)),
            User(email="admin@example.com", name="Admin One", role="admin", password_hash=hash_password(PASSWORD)),
        ])
        db.commit()
    yield
    engine.dispose()
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_limiter():
    auth_limiter.reset()


class Client:
    """TestClient wrapper that sends the CSRF header like the frontend does."""

    def __init__(self):
        self.c = TestClient(app)

    def _h(self):
        tok = self.c.cookies.get("es_csrf")
        return {"X-CSRF-Token": tok} if tok else {}

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, **kw):
        return self.c.post(url, headers=self._h() | kw.pop("headers", {}), **kw)

    def put(self, url, **kw):
        return self.c.put(url, headers=self._h() | kw.pop("headers", {}), **kw)

    def patch(self, url, **kw):
        return self.c.patch(url, headers=self._h() | kw.pop("headers", {}), **kw)

    def delete(self, url, **kw):
        return self.c.delete(url, headers=self._h() | kw.pop("headers", {}), **kw)

    def login(self, email, password=PASSWORD):
        r = self.c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()


_n = [0]


def new_worker(city="Chennai", work_type="rider") -> Client:
    _n[0] += 1
    c = Client()
    r = c.c.post("/api/auth/register", json={"email": f"worker{_n[0]}@example.com", "password": PASSWORD,
                                             "name": f"Worker {_n[0]}", "city": city, "work_type": work_type})
    assert r.status_code == 201, r.text
    return c


@pytest.fixture
def worker() -> Client:
    return new_worker()


@pytest.fixture
def officer() -> Client:
    c = Client()
    c.login("officer@example.com")
    return c


@pytest.fixture
def admin() -> Client:
    c = Client()
    c.login("admin@example.com")
    return c


def life_files(idx=1, weeks=40, wt="rider", accounts=2):
    """A generated life written in two bank formats plus payout statements (same writers as the seeded data)."""
    from app.sim import generate as g
    from app.sim.life import live, make_persona

    p = make_persona(np.random.default_rng(idx), idx, f"Worker {idx}", "Chennai", wt, weeks, accounts)
    life = live(p, seed=idx)
    files = {"bank0": g.bank_csv_pallava(life, 0, g.account_no(p, 0))}
    if accounts > 1:
        files["bank1"] = g.bank_csv_konark(life, 1, g.account_no(p, 1))
    for plat in p.platforms:
        files[plat] = g.payout_csv(life, plat)
    return life, files


def upload(c: Client, kind: str, name: str, data: bytes, platform: str = "", account_ref: str = ""):
    cons = c.post("/api/worker/consents", json={"source_kind": kind, "purpose": "income_assessment"}).json()
    r = c.post("/api/worker/sources", data={"kind": kind, "consent_id": str(cons["id"]), "platform": platform,
                                            "account_ref": account_ref}, files={"file": (name, data)})
    return r, cons
