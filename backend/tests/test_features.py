"""Features & menus: role defaults, per-user grants by the Super Administrator, and the permission guard."""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import User
from tests.conftest import login

A = "/api/v1"
PW = "Demo!2026pass"
SUPER = ("admin@lishebora.local", "ChangeMe!2026")


def uid(email):
    with SessionLocal() as db:
        return str(db.scalar(select(User.id).where(User.email == email)))


def test_role_menus_are_trimmed(client):
    me = client.get(f"{A}/auth/me", headers=login(client, "evaluator1@demo.lishebora", PW)).json()
    assert set(me["menu"]) == {"/app", "/app/notifications", "/app/profile", "/app/evaluations"}
    sch = client.get(f"{A}/auth/me", headers=login(client, "school.admin@demo.lishebora", PW)).json()["menu"]
    assert "/app/demand" in sch and "/app/deliveries" in sch and "/app/sourcing" not in sch and "/app/budgets" not in sch
    sup = client.get(f"{A}/auth/me", headers=login(client, "supplier2@demo.lishebora", PW)).json()["menu"]
    assert "/app/opportunities" in sup and "/app/locations" not in sup


def test_super_admin_grants_and_removes_features(client):
    sa = login(client, *SUPER)
    ev = uid("evaluator1@demo.lishebora")
    page = client.get(f"{A}/users/{ev}/features", headers=sa).json()
    rows = {r["page"]: r for r in page["pages"]}
    assert rows["/app/evaluations"]["status"] == "default"
    assert rows["/app/suppliers"]["status"] == "available"          # evaluators may view suppliers
    assert rows["/app/invoices"]["status"] == "needs_role" and rows["/app/invoices"]["needs"]
    # a page the roles do not allow cannot be granted
    r = client.put(f"{A}/users/{ev}/features", headers=sa, json={"add": ["/app/invoices"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "NEEDS_ROLE"
    r = client.put(f"{A}/users/{ev}/features", headers=sa, json={"add": ["/app/suppliers"]})
    assert r.status_code == 200 and "/app/suppliers" in r.json()["menu"]
    assert "/app/suppliers" in client.get(f"{A}/auth/me", headers=login(client, "evaluator1@demo.lishebora", PW)).json()["menu"]
    client.put(f"{A}/users/{ev}/features", headers=sa, json={"add": [], "remove": ["/app/evaluations"]})
    assert "/app/evaluations" not in client.get(f"{A}/auth/me", headers=login(client, "evaluator1@demo.lishebora", PW)).json()["menu"]
    client.put(f"{A}/users/{ev}/features", headers=sa, json={"add": [], "remove": []})


def test_role_defaults_editable_by_super_admin_only(client):
    admin = login(client, "administrator@demo.lishebora", PW)
    assert client.get(f"{A}/features", headers=admin).json()["error"]["code"] == "SUPER_ADMIN_ONLY"
    sa = login(client, *SUPER)
    cat = client.get(f"{A}/features", headers=sa).json()
    drv = next(r for r in cat["roles"] if r["key"] == "driver")
    assert drv["pages"] == ["/app/deliveries"] and "/app/deliveries" in drv["possible"]
    r = client.put(f"{A}/features/roles/driver", headers=sa, json={"pages": ["/app/deliveries", "/app/complaints"]}).json()
    assert r["customised"] and "/app/complaints" in client.get(f"{A}/auth/me", headers=login(client, "driver@demo.lishebora", PW)).json()["menu"]
    assert client.post(f"{A}/features/roles/driver/reset", headers=sa).json()["customised"] is False
    assert "/app/complaints" not in client.get(f"{A}/auth/me", headers=login(client, "driver@demo.lishebora", PW)).json()["menu"]
