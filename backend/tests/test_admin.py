"""Administrator accounts: separate sign-in, admin-only accounts, super-admin-only management, full content rights."""
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import User
from tests.conftest import login, make_user, org_id

A = "/api/v1"
SUPER = ("admin@lishebora.local", "ChangeMe!2026")
ADMIN = ("administrator@demo.lishebora", "Demo!2026pass")
DEMO_PW = "Demo!2026pass"


def _err(r):
    return r.json()["error"]["code"]


def test_separate_sign_in(client):
    for who, pw in (SUPER, ADMIN):
        r = client.post(f"{A}/auth/login", json={"identifier": who, "password": pw})
        assert r.status_code == 403 and _err(r) == "USE_ADMIN_SIGN_IN" and r.json()["error"]["details"][0]["href"] == "/admin/sign-in"
        r = client.post(f"{A}/auth/admin/login", json={"identifier": who, "password": pw}).json()
        assert r["mfa_required"] and r["mfa_token"]
    # wrong password on the admin page gives the normal generic error
    assert _err(client.post(f"{A}/auth/admin/login", json={"identifier": ADMIN[0], "password": "nope-nope-1A"})) == "INVALID_CREDENTIALS"
    # operational users cannot use the admin page
    r = client.post(f"{A}/auth/admin/login", json={"identifier": "procurement@demo.lishebora", "password": DEMO_PW})
    assert r.status_code == 403 and _err(r) == "NOT_AN_ADMIN"
    # the MFA step checks which sign-in page issued the token
    ta = client.post(f"{A}/auth/admin/login", json={"identifier": ADMIN[0], "password": ADMIN[1]}).json()
    from app.core.security import create_token, decode_token
    wrong = create_token(decode_token(ta["mfa_token"], "mfa")["sub"], "mfa", 5, {"portal": "app"})
    assert _err(client.post(f"{A}/auth/mfa/verify", json={"mfa_token": wrong, "code": ta["dev_code"]})) == "USE_ADMIN_SIGN_IN"
    done = client.post(f"{A}/auth/mfa/verify", json={"mfa_token": ta["mfa_token"], "code": ta["dev_code"]})
    assert done.status_code == 200
    me = client.get(f"{A}/auth/me", headers={"Authorization": f"Bearer {done.json()['access_token']}"}).json()
    assert me["is_admin"] and not me["is_super_admin"] and me["roles"][0]["role_name"] == "Administrator"


def test_admin_accounts_hold_no_other_roles_and_only_super_manages_them(client):
    sh, ah = login(client, *SUPER), login(client, *ADMIN)
    # Administrator cannot create administrators; Super Administrator can
    body = {"full_name": "Second Admin", "email": "admin2@lishebora-pilot.org", "role": "system_admin"}
    assert _err(client.post(f"{A}/users/invite", headers=ah, json=body)) == "SUPER_ADMIN_ONLY"
    new = client.post(f"{A}/users/invite", headers=sh, json=body)
    assert new.status_code == 201, new.text
    nid = new.json()["id"]
    # no operational role on an administrator account, and no admin role on an operational account
    assert _err(client.post(f"{A}/users/{nid}/roles", headers=sh, json={"role": "county_finance_officer", "org_id": str(org_id("MAKUENI"))})) == "ADMIN_ROLE_SEPARATE"
    uid = make_user("ops.person@test.ke", "logistics_officer", "MAKUENI")
    assert _err(client.post(f"{A}/users/{uid}/roles", headers=sh, json={"role": "system_admin"})) == "ADMIN_ROLE_SEPARATE"
    # an Administrator cannot suspend another administrator, but manages other users
    assert _err(client.post(f"{A}/users/{nid}/status", headers=ah, json={"status": "suspended"})) == "SUPER_ADMIN_ONLY"
    assert client.post(f"{A}/users/{uid}/status", headers=ah, json={"status": "suspended"}).status_code == 200
    # SMS-code sign-in is not available to administrators
    with SessionLocal() as db:
        u = db.get(User, __import__("uuid").UUID(nid))
        u.phone = "+254799000555"
        db.commit()
    assert client.post(f"{A}/auth/otp/request", json={"phone": "0799000555"}).json()["dev_code"] is None
    # importing administrator roles is refused
    csv = "full_name,email,phone,role,org_code\nX Admin,xa@x.ke,,system_admin,\n"
    r = client.post(f"{A}/system/import/users", headers=sh, files={"file": ("u.csv", csv, "text/csv")}).json()
    assert r["errors"] == 1


def test_administrator_manages_all_content(client):
    ah = login(client, *ADMIN)
    # website: create, publish
    n = client.post(f"{A}/cms/news", headers=ah, json={"title": "Admin news item", "summary": "s", "body": "b", "category": "Announcement"})
    assert n.status_code == 201, n.text
    nid = n.json()["id"]
    client.post(f"{A}/cms/news/{nid}/workflow", headers=ah, json={"action": "submit"})
    pub = client.post(f"{A}/cms/news/{nid}/workflow", headers=ah, json={"action": "publish"})
    assert pub.status_code == 200 and pub.json()["status"] == "published", pub.text
    assert any(x["title"] == "Admin news item" for x in client.get(f"{A}/public/news").json())
    # master data: commodities (food categories are validated) and schools (rename, NEMIS code)
    bad = client.post(f"{A}/commodities", headers=ah, json={"code": "Qx", "name": "Quinoa", "category": "cereals"})
    assert bad.status_code == 422
    ok = client.post(f"{A}/commodities", headers=ah, json={"code": "finger-millet", "name": "Finger millet", "category": "whole_grains"}).json()
    assert ok["code"] == "FINGER-MILLET" and ok["food_group"] == "Cereal"
    sid = org_id("ISIOLO-SCH008")
    r = client.put(f"{A}/orgs/{sid}", headers=ah, json={"name": "Yaqbarsadhi Primary", "code": "ISIOLO-SCH008"})
    assert r.status_code == 200 and r.json()["name"] == "Yaqbarsadhi Primary"
    assert client.get(f"{A}/system/status", headers=ah).status_code == 200
    assert client.get(f"{A}/users", headers=ah).json()["total"] > 10
    # read-only on operations: cannot approve a supplier or pay
    me = client.get(f"{A}/auth/me", headers=ah).json()
    assert "cms:approve" in me["permissions"] and "md:approve" in me["permissions"]
    assert not {"fin:pay", "eva:approve", "sup:approve", "src:create"} & set(me["permissions"])
