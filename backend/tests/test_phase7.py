"""Phase 7 (pilot readiness): outbox & SMS adapter, background jobs, CSRF origin check, rate limits, readiness,
production settings guard, and CSV onboarding of schools and users."""
from datetime import timedelta

import uuid

import httpx
import pytest
from sqlalchemy import select, update

from app import jobs
from app.core import protection
from app.core.config import Settings, settings, validate
from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.models import Organization, OutboundMessage, User, WorkflowInstance
from app.services import notify
from tests.conftest import login, org_id
from tests.test_phase4 import A, h, hub, make_cleared_batch

ADMIN = ("admin@lishebora.local", "ChangeMe!2026")


def test_outbox_redacts_codes_and_retries_gateway(client, monkeypatch):
    login(client, *ADMIN)                       # MFA code goes out by SMS/email
    with SessionLocal() as db:
        m = db.scalars(select(OutboundMessage).where(OutboundMessage.sensitive.is_(True)).order_by(OutboundMessage.created_at.desc())).first()
        assert m.status == "sent" and m.body.startswith("[redacted") and m.provider == "console"
    # gateway down: message stays queued with the error, then the worker delivers it
    monkeypatch.setattr(settings, "notify_backend", "africastalking")
    monkeypatch.setattr(settings, "at_api_key", "k")

    def down(*a, **k):
        raise httpx.ConnectError("no route")
    monkeypatch.setattr(httpx, "post", down)
    with SessionLocal() as db:
        msg = notify.sms(db, "0712000999", "Test message")
        db.commit()
        assert msg.status == "queued" and "no route" not in msg.last_error     # non-urgent: not attempted yet
        db.execute(update(OutboundMessage).where(OutboundMessage.id == msg.id).values(next_attempt_at=utcnow() - timedelta(minutes=1)))
        db.commit()
        r = notify.send_queued(db)
        assert r["failed"] >= 1
        db.refresh(msg)
        assert msg.status == "queued" and "no route" in msg.last_error and msg.attempts == 1

    class Ok:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"SMSMessageData": {"Recipients": [{"status": "Success", "messageId": "ATX-1"}]}}
    sent = {}
    monkeypatch.setattr(httpx, "post", lambda url, **k: sent.update(url=url, data=k["data"]) or Ok())
    with SessionLocal() as db:
        db.execute(update(OutboundMessage).where(OutboundMessage.id == msg.id).values(next_attempt_at=utcnow() - timedelta(minutes=1)))
        db.commit()
        notify.send_queued(db)
        m2 = db.get(OutboundMessage, msg.id)
        assert m2.status == "sent" and m2.provider_ref == "ATX-1"
    assert sent["data"]["to"] == "+254712000999" and "sandbox" in sent["url"]


def test_jobs_remind_overdue_approvals(client):
    bid, _ = make_cleared_batch(client, commodity="BEANS", qtys=(40,), moisture=12)
    r = client.post(f"{A}/inventory/adjustments", headers=h(client, "aggregator"),
                    json={"location_id": hub(), "batch_id": bid, "quantity": "-1", "type": "waste", "reason": "Sample for lab test"}).json()
    with SessionLocal() as db:
        db.execute(update(WorkflowInstance).where(WorkflowInstance.id == uuid.UUID(r["workflow"]["id"])).values(stage_due_at=utcnow() - timedelta(days=5)))
        db.commit()
    out = jobs.run(list(jobs.TASKS))
    assert all("error" not in v for v in out.values()), out
    assert out["sla"]["reminded"] >= 1
    notes = client.get(f"{A}/notifications", headers=h(client, "warehouse.supervisor")).json()["items"]
    assert any(n["title"].startswith("Overdue approval") for n in notes)
    assert jobs.run(["sla"])["sla"]["reminded"] == 0          # idempotent: no second reminder the same day
    st = client.get(f"{A}/system/status", headers=login(client, *ADMIN)).json()
    assert "sla" in st["jobs"] and st["outbox"]["sent"] >= 1


def test_csrf_origin_rate_limit_and_readiness(client, monkeypatch):
    c2 = type(client)(client.app)
    r = c2.post(f"{A}/auth/login", json={"identifier": "meals.officer@demo.lishebora", "password": "Demo!2026pass"})
    assert r.status_code == 200 and "lb_access" in c2.cookies
    evil = c2.post(f"{A}/notifications/read", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403 and evil.json()["error"]["code"] == "CSRF_ORIGIN"
    assert c2.post(f"{A}/notifications/read", headers={"Origin": "http://localhost:3000"}).status_code == 200
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    protection._hits.clear()
    codes = [client.post(f"{A}/auth/login", json={"identifier": "nobody@x.ke", "password": "wrong-password"}).status_code for _ in range(12)]
    assert codes[-1] == 429 and 429 not in codes[:10]
    protection._hits.clear()
    assert client.get("/api/health/ready").json()["checks"] == {"database": "ok", "storage": "ok"}


def test_production_guard():
    with pytest.raises(RuntimeError) as e:
        validate(Settings(app_env="production", jwt_secret="x" * 40, bid_encryption_key="k", debug=True, cookie_secure=False,
                          database_url="sqlite:///x.db"))
    msg = str(e.value)
    assert "DEBUG" in msg and "COOKIE_SECURE" in msg and "PostgreSQL" in msg and "SEED_ADMIN_PASSWORD" in msg
    ok = Settings(app_env="production", jwt_secret="x" * 40, bid_encryption_key="k", debug=False, cookie_secure=True,
                  database_url="postgresql+psycopg://u:p@db/x", seed_admin_password="Another!2026pass")
    assert validate(ok) is ok


def test_csv_onboarding(client):
    ah = login(client, *ADMIN)
    csv = ("county,sub_county,cluster,school_code,school_name,enrolment,lat,lng\n"
           "Makueni County,North Ward,Cluster 7,MAKUENI-SCH101,Mwangaza Primary,512,0.61,34.55\n"
           "Makueni County,North Ward,,MAKUENI-SCH102,Tumaini Primary,abc,,\n"
           "Nowhere County,X,,PILOT-Z-1,Lost School,10,,\n")
    r = client.post(f"{A}/system/import/schools", headers=ah, files={"file": ("s.csv", csv, "text/csv")}).json()
    assert r["create"] == 1 and r["errors"] == 2 and not r["committed"]
    bad = client.post(f"{A}/system/import/schools?commit=true", headers=ah, files={"file": ("s.csv", csv, "text/csv")})
    assert bad.status_code == 422 and org_id("MAKUENI-SCH101") is None           # all-or-nothing
    good = csv.splitlines()[0] + "\n" + csv.splitlines()[1] + "\nMakueni County,North Ward,,MAKUENI-SCH102,Tumaini Primary,380,,\n"
    r = client.post(f"{A}/system/import/schools?commit=true", headers=ah, files={"file": ("s.csv", good, "text/csv")}).json()
    assert r["committed"] and r["create"] == 2
    with SessionLocal() as db:
        s = db.scalar(select(Organization).where(Organization.code == "MAKUENI-SCH101"))
        assert s.meta["enrolment"] == 512 and s.meta["gps"]["lat"] == 0.61
        assert db.get(Organization, s.parent_id).name == "Cluster 7"
    again = client.post(f"{A}/system/import/schools", headers=ah, files={"file": ("s.csv", good, "text/csv")}).json()
    assert again["update"] == 2
    users = ("full_name,email,phone,role,org_code\n"
             "Jane Wanjiru,jane.w@school.ke,,school_admin,MAKUENI-SCH101\n"
             "Peter Otieno,,0799000111,school_meals_officer,MAKUENI-SCH101\n"
             "Sam Supplier,sam@x.ke,,supplier,MAKUENI\n"
             "Double Role,dr@x.ke,,aggregator,MAKUENI\n")
    r = client.post(f"{A}/system/import/users", headers=ah, files={"file": ("u.csv", users, "text/csv")}).json()
    assert r["create"] == 2 and r["errors"] == 2
    ok = "\n".join(users.splitlines()[:3]) + "\nFin One,fin1@x.ke,,finance_officer,MAKUENI\nFin One,fin1@x.ke,,county_finance_officer,MAKUENI\n"
    r = client.post(f"{A}/system/import/users", headers=ah, files={"file": ("u.csv", ok, "text/csv")}).json()
    assert any("segregation" in " ".join(x["errors"]) for x in r["lines"])        # conflicting pair in the same file
    ok = "\n".join(users.splitlines()[:3]) + "\n"
    r = client.post(f"{A}/system/import/users?commit=true", headers=ah, files={"file": ("u.csv", ok, "text/csv")}).json()
    assert r["committed"] and r["create"] == 2
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "jane.w@school.ke")) is not None
        m = db.scalar(select(OutboundMessage).where(OutboundMessage.to == "jane.w@school.ke"))
        assert m.sensitive and m.subject == "LisheBora invitation"
    assert client.post(f"{A}/system/import/users", headers=h(client, "procurement"), files={"file": ("u.csv", ok, "text/csv")}).status_code == 403
