import io

from tests.conftest import PW, login, make_user, org_id

PDF = b"%PDF-1.4\n%demo\n"


def _register(client, name, phone, county="MAKUENI"):
    body = {"account_type": "trader", "legal_name": name, "contact_name": name, "phone": phone,
            "county_id": str(org_id(county)), "accept_terms": True, "password": PW}
    reg = client.post("/api/v1/auth/register/supplier", json=body).json()
    client.post("/api/v1/auth/verify-phone", json={"user_id": reg["user_id"], "code": reg["dev_code"]})
    client.cookies.clear()
    return reg["supplier_id"]


def test_permissions_enforced(client):
    make_user("school@test.ke", "school_meals_officer", "MAKUENI-SCH001")
    h = login(client, "school@test.ke")
    assert client.get("/api/v1/users", headers=h).json()["error"]["code"] == "FORBIDDEN"
    assert client.get("/api/v1/cms/news", headers=h).status_code == 403


def test_data_scope_county(client):
    a = _register(client, "Trader A", "0733000001", "MAKUENI")
    b = _register(client, "Trader B", "0733000002", "EMBU")
    make_user("cpoa@test.ke", "county_procurement_officer", "MAKUENI")
    h = login(client, "cpoa@test.ke")
    names = [s["legal_name"] for s in client.get("/api/v1/suppliers", headers=h).json()["items"]]
    assert "Trader A" in names and "Trader B" not in names
    assert client.get(f"/api/v1/suppliers/{b}", headers=h).json()["error"]["code"] == "OUT_OF_SCOPE"
    assert client.get(f"/api/v1/suppliers/{a}", headers=h).status_code == 200


def test_prequalification_workflow(client):
    sid = _register(client, "Trader C", "0733000003", "MAKUENI")
    # supplier uploads docs
    sh = login(client, "0733000003")
    for t in ("registration", "bank"):
        r = client.post(f"/api/v1/suppliers/{sid}/documents", headers=sh, data={"doc_type": t},
                        files={"file": ("x.pdf", io.BytesIO(PDF), "application/pdf")})
        assert r.status_code == 201, r.text
    bad = client.post(f"/api/v1/suppliers/{sid}/documents", headers=sh, data={"doc_type": "other"},
                      files={"file": ("x.exe", io.BytesIO(b"MZ\x90"), "application/pdf")})
    assert bad.json()["error"]["code"] == "FILE_TYPE"
    # county procurement officer verifies; county admin approves
    make_user("cpoa@test.ke", "county_procurement_officer", "MAKUENI")
    make_user("cadm@test.ke", "county_admin", "MAKUENI")
    ph = login(client, "cpoa@test.ke")
    assert client.post(f"/api/v1/suppliers/{sid}/review", headers=ph, json={"to_status": "under_review"}).status_code == 200
    # officer cannot approve (no sup:approve)
    assert client.post(f"/api/v1/suppliers/{sid}/review", headers=ph, json={"to_status": "approved"}).status_code == 403
    ah = login(client, "cadm@test.ke")
    r = client.post(f"/api/v1/suppliers/{sid}/review", headers=ah, json={"to_status": "approved"})
    assert r.json()["error"]["code"] == "DOCUMENTS_INCOMPLETE"
    docs = client.get(f"/api/v1/suppliers/{sid}", headers=ph).json()["documents"]
    for d in docs:
        assert client.post(f"/api/v1/suppliers/{sid}/documents/{d['id']}/review", headers=ph,
                           json={"status": "verified"}).status_code == 200
    assert client.post(f"/api/v1/suppliers/{sid}/review", headers=ah, json={"to_status": "approved"}).status_code == 200
    r = client.post(f"/api/v1/suppliers/{sid}/review", headers=ah,
                    json={"to_status": "prequalified", "approved_categories": ["refined_grains"]})
    assert r.json()["status"] == "prequalified"
    skip = client.post(f"/api/v1/suppliers/{sid}/review", headers=ah, json={"to_status": "submitted"})
    assert skip.json()["error"]["code"] == "INVALID_TRANSITION"


def test_sod_role_conflict_and_self_assign(client):
    admin = login(client, "admin@lishebora.local", "ChangeMe!2026")
    uid = make_user("fin@test.ke", "finance_officer", "MAKUENI")
    r = client.post(f"/api/v1/users/{uid}/roles", headers=admin, json={"role": "county_finance_officer",
                                                                        "org_id": str(org_id("MAKUENI"))})
    assert r.json()["error"]["code"] == "SOD_CONFLICT"
    me = client.get("/api/v1/auth/me", headers=admin).json()
    r = client.post(f"/api/v1/users/{me['id']}/roles", headers=admin, json={"role": "auditor"})
    assert r.json()["error"]["code"] == "SOD_SELF_ASSIGN"


def test_audit_log_written_and_readonly(client):
    admin = login(client, "admin@lishebora.local", "ChangeMe!2026")
    rows = client.get("/api/v1/audit", headers=admin).json()["items"]
    assert any(r["action"] == "REGISTER" for r in rows)
    assert client.delete("/api/v1/audit", headers=admin).status_code == 405


def test_supplier_implied_view_is_own_record_only(client):
    _register(client, "Trader D", "0733000004", "MAKUENI")
    _register(client, "Trader E", "0733000005", "MAKUENI")
    h = login(client, "0733000004")
    names = [s["legal_name"] for s in client.get("/api/v1/suppliers", headers=h).json()["items"]]
    assert names == ["Trader D"]


def test_admin_can_list_users(client):
    admin = login(client, "admin@lishebora.local", "ChangeMe!2026")
    assert client.get("/api/v1/users", headers=admin).json()["total"] >= 1
