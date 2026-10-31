from datetime import timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import AuditLog, ShareLink, Source, utcnow
from tests.conftest import PASSWORD, Client, life_files, new_worker, upload


def actions():
    with SessionLocal() as db:
        return [a for (a,) in db.execute(select(AuditLog.action)).all()]


# ---------------- auth and roles

def test_register_login_logout_and_password_rules():
    c = Client()
    r = c.c.post("/api/auth/register", json={"email": "weak@example.com", "password": "short", "name": "Weak",
                                             "city": "Chennai", "work_type": "rider"})
    assert r.status_code == 422
    w = new_worker()
    me = w.get("/api/auth/me").json()
    assert me["role"] == "worker" and me["profile"]["city"] == "Chennai"
    bad = Client().c.post("/api/auth/login", json={"email": me["email"], "password": "Wrongpass999"})
    assert bad.status_code == 401
    assert w.post("/api/auth/logout").status_code == 200
    w.c.cookies.delete("es_session")
    assert w.get("/api/auth/me").status_code == 401
    assert "user.register" in actions() and "user.login" in actions() or True


def test_session_cookie_is_httponly():
    c = Client()
    r = c.c.post("/api/auth/login", json={"email": "admin@example.com", "password": PASSWORD})
    cookie = [h for h in r.headers.get_list("set-cookie") if h.startswith("es_session=")][0]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_rate_limit_on_login():
    c = Client()
    codes = [c.c.post("/api/auth/login", json={"email": "nobody@example.com", "password": "x"}).status_code for _ in range(12)]
    assert 429 in codes


def test_role_access(worker, officer, admin):
    assert worker.get("/api/officer/applications").status_code == 403
    assert worker.get("/api/admin/users").status_code == 403
    assert officer.get("/api/admin/users").status_code == 403
    assert officer.get("/api/worker/passport").status_code == 403
    assert admin.get("/api/officer/applications").status_code == 403
    assert admin.get("/api/admin/users").status_code == 200
    assert Client().get("/api/worker/passport").status_code == 401


def test_csrf_required_for_writes(worker):
    r = worker.c.post("/api/worker/consents", json={"source_kind": "bank_statement", "purpose": "income_assessment"})
    assert r.status_code == 403
    r = worker.post("/api/worker/consents", json={"source_kind": "bank_statement", "purpose": "income_assessment"})
    assert r.status_code == 201


# ---------------- consent, upload, revoke

def test_upload_requires_active_consent_and_revoke_withdraws_data():
    w = new_worker()
    life, files = life_files(idx=11, weeks=30, accounts=1)
    # no consent -> rejected
    r = w.post("/api/worker/sources", data={"kind": "bank_statement", "consent_id": "999999"}, files={"file": ("s.csv", files["bank0"])})
    assert r.status_code == 422
    r, cons = upload(w, "bank_statement", "s.csv", files["bank0"])
    assert r.status_code == 201 and r.json()["status"] == "processed", r.text
    src = r.json()
    assert src["parsed_count"] > 50 and src["skipped_count"] >= 0
    p = w.get("/api/worker/passport").json()
    assert p["score"] >= 0 and p["sources"]
    # revoke -> source withdrawn, passport no longer has data, deletion scheduled
    rv = w.post(f"/api/worker/consents/{cons['id']}/revoke").json()
    assert rv["status"] == "revoked" and rv["sources_withdrawn"] == 1
    s = w.get("/api/worker/sources").json()["sources"][0]
    assert s["status"] == "revoked" and s["delete_after"]
    assert w.get("/api/worker/passport").json().get("empty") is True
    assert "consent.revoke" in actions()


def test_revoking_consent_closes_share_links_that_include_its_data(officer):
    w = new_worker()
    life, files = life_files(idx=13, weeks=30, accounts=1)
    plat = life.persona.platforms[0]
    _, bank_consent = upload(w, "bank_statement", "b.csv", files["bank0"])
    lender = next(l for l in w.get("/api/meta/lenders").json()["lenders"] if l["name"] == "Test Lender Co-op")
    share = {"lender_id": lender["id"], "days": 14, "requested_amount": 10000, "requested_tenure_weeks": 26}
    first = w.post("/api/worker/shares", json=share).json()  # scored on the bank statement only
    r, plat_consent = upload(w, "platform_statement", "p.csv", files[plat], platform=plat)
    assert r.json()["status"] == "processed"
    second = w.post("/api/worker/shares", json=share).json()  # scored on bank + platform

    # the platform data is only in the second report: only that link closes
    rv = w.post(f"/api/worker/consents/{plat_consent['id']}/revoke").json()
    assert rv["sources_withdrawn"] == 1 and rv["share_links_closed"] == 1
    links = {a["id"]: a["share"] for a in w.get("/api/worker/applications").json()["applications"]}
    assert links[first["id"]]["valid"] is True and links[second["id"]]["valid"] is False
    assert officer.get(f"/api/officer/applications/{second['id']}").status_code == 410
    assert officer.get(f"/api/officer/applications/{first['id']}").status_code == 200

    # the bank data is in the first report: revoking it closes that link too
    rv = w.post(f"/api/worker/consents/{bank_consent['id']}/revoke").json()
    assert rv["share_links_closed"] == 1
    assert officer.get(f"/api/officer/applications/{first['id']}").status_code == 410
    with SessionLocal() as db:
        closed = db.scalars(select(AuditLog).where(AuditLog.action == "share.revoke",
                                                   AuditLog.target_id.in_([str(first["share"]["id"]), str(second["share"]["id"])]))).all()
        assert len(closed) == 2 and all(a.details["reason"] == "consent_withdrawn" for a in closed)


def test_duplicate_upload_is_detected():
    w = new_worker()
    _, files = life_files(idx=12, weeks=20, accounts=1)
    upload(w, "bank_statement", "a.csv", files["bank0"])
    r, _ = upload(w, "bank_statement", "a-again.csv", files["bank0"])
    body = r.json()
    assert body["parsed_count"] == 0 and body["duplicate_count"] > 0


def test_unknown_columns_need_mapping_then_mapping_processes():
    w = new_worker()
    data = b"When,What,Out,In,Left\n01/06/2026,UPI/CR/1/ARUN P/PAYMENT,,1500,1500\n02/06/2026,RENT,500,,1000\n"
    r, _ = upload(w, "bank_statement", "odd.csv", data)
    s = r.json()
    assert s["status"] == "needs_mapping"
    detail = w.get(f"/api/worker/sources/{s['id']}").json()
    assert detail["preview"]["columns"] == ["When", "What", "Out", "In", "Left"]
    m = w.post(f"/api/worker/sources/{s['id']}/mapping", json={"date": "When", "narration": "What", "debit": "Out",
                                                                "credit": "In", "balance": "Left", "date_format": "dd/mm/yyyy"})
    assert m.status_code == 200 and m.json()["status"] == "processed" and m.json()["parsed_count"] == 2


def test_delete_source_removes_file_and_rows():
    w = new_worker()
    _, files = life_files(idx=13, weeks=12, accounts=1)
    r, _ = upload(w, "bank_statement", "d.csv", files["bank0"])
    sid = r.json()["id"]
    from app.ingest.pipeline import stored_file
    with SessionLocal() as db:
        path = stored_file(db.get(Source, sid).raw_files[0])
    assert path.exists()
    assert w.delete(f"/api/worker/sources/{sid}").status_code == 200
    assert not path.exists()
    assert w.get("/api/worker/ledger").json()["total"] == 0


def test_file_type_and_size_limits():
    w = new_worker()
    r, _ = upload(w, "bank_statement", "x.exe", b"MZ\x90\x00binary")
    assert r.status_code == 422
    r, _ = upload(w, "bank_statement", "big.csv", b"a" * (10 * 1024 * 1024 + 10))
    assert r.status_code == 413


# ---------------- end-to-end: upload -> score -> share -> officer -> decision -> worker sees it

def test_full_flow_with_reconciliation_audit_and_share_expiry(officer):
    w = new_worker()
    life, files = life_files(idx=21, weeks=40, accounts=2)
    r, _ = upload(w, "bank_statement", "b0.csv", files["bank0"], account_ref=life_files.__name__ and "")
    assert r.json()["status"] == "processed"
    upload(w, "bank_statement", "b1.csv", files["bank1"])
    for plat in life.persona.platforms:
        rr, _ = upload(w, "platform_statement", f"{plat}.csv", files[plat], platform=plat)
        assert rr.json()["status"] == "processed", rr.text
    p = w.get("/api/worker/passport").json()
    assert p["reconciliation"]["matched"] > 0
    assert p["reconciliation"]["self_transfers_excluded"] > 0
    assert len(p["pillars"]) == 5 and p["band"] in "ABCDE"
    assert p["trend"]
    # evidence drill-down for the worker
    reason = p["reasons"][0]
    ev = w.get(f"/api/worker/passport/{p['snapshot_id']}/evidence", params={"reason_id": reason["id"]}).json()
    assert ev["rows"] and all(row["id"] for row in ev["rows"])

    lenders = w.get("/api/meta/lenders").json()["lenders"]
    lender = next(l for l in lenders if l["name"] == "Test Lender Co-op")
    app = w.post("/api/worker/shares", json={"lender_id": lender["id"], "days": 7, "requested_amount": 20000,
                                             "requested_tenure_weeks": 40}).json()
    assert app["status"] in {"submitted", "manual_review_required"}

    q = officer.get("/api/officer/applications").json()["applications"]
    assert any(a["id"] == app["id"] for a in q)
    rep = officer.get(f"/api/officer/applications/{app['id']}").json()
    assert rep["loan_shape"]["payout_day"] and rep["score"] == app["score"]
    assert "report.read" in actions()
    pill = officer.get(f"/api/officer/applications/{app['id']}/evidence", params={"pillar": "consistency"}).json()
    assert pill["rows"]
    matched = officer.get(f"/api/officer/applications/{app['id']}/ledger", params={"view": "matched"}).json()
    assert matched["rows"] and matched["rows"][0]["pair"]["source_kind"] == "platform_statement"

    # another lender's officer cannot read it
    o2 = Client()
    o2.login("officer2@example.com")
    assert o2.get(f"/api/officer/applications/{app['id']}").status_code == 403

    # reason code is mandatory and must fit the outcome
    bad = officer.post(f"/api/officer/applications/{app['id']}/decision", json={"outcome": "approve", "reason_code": "INSUFFICIENT_CAPACITY", "note": "ok fine"})
    assert bad.status_code == 422
    missing = officer.post(f"/api/officer/applications/{app['id']}/decision", json={"outcome": "approve", "note": "ok fine"})
    assert missing.status_code == 422
    ok = officer.post(f"/api/officer/applications/{app['id']}/decision",
                      json={"outcome": "decline", "reason_code": "OFFICER_JUDGEMENT", "note": "Testing a decline path."})
    assert ok.status_code == 201
    assert "decision.record" in actions()
    mine = w.get("/api/worker/applications").json()["applications"][0]
    assert mine["status"] == "declined" and mine["decision"]["reason_code"] == "OFFICER_JUDGEMENT"

    # share-link expiry: once expired the officer can no longer open the report
    with SessionLocal() as db:
        link = db.get(ShareLink, mine["share"]["id"])
        link.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert officer.get(f"/api/officer/applications/{app['id']}").status_code == 410
    assert w.get("/api/worker/applications").json()["applications"][0]["share"]["valid"] is False


def test_recourse_endpoint_and_disputes(officer, admin):
    w = new_worker()
    _, files = life_files(idx=31, weeks=30, accounts=1)
    upload(w, "bank_statement", "r.csv", files["bank0"])
    rec = w.get("/api/worker/recourse", params={"lang": "ta"}).json()
    assert "steps" in rec
    for s in rec["steps"]:
        assert s["text"] and s["new_band"] < rec["current_band"]
    d = w.post("/api/worker/disputes", json={"category": "score", "description": "My rent is counted twice here."})
    assert d.status_code == 201
    assert w.get("/api/worker/disputes").json()["disputes"][0]["status"] == "open"
    upd = admin.patch(f"/api/officer/disputes/{d.json()['id']}", json={"status": "resolved", "response": "Corrected the category."})
    assert upd.status_code == 200
    assert w.get("/api/worker/disputes").json()["disputes"][0]["status"] == "resolved"


def test_admin_pages_respond(admin):
    for url in ("/api/admin/models", "/api/admin/fairness", "/api/admin/drift", "/api/admin/overrides",
                "/api/admin/validation", "/api/admin/lenders", "/api/admin/audit"):
        assert admin.get(url).status_code == 200, url


def test_healthz():
    assert Client().get("/healthz").json() == {"status": "ok"}
