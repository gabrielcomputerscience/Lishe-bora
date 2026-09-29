from tests.conftest import PW, login, make_user, org_id


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_error_envelope(client):
    r = client.get("/api/v1/auth/me")
    body = r.json()
    assert r.status_code == 401 and body["success"] is False and body["error"]["code"] == "UNAUTHENTICATED"
    assert body["correlation_id"]


def test_admin_login_requires_mfa(client):
    r = client.post("/api/v1/auth/admin/login", json={"identifier": "admin@lishebora.local", "password": "ChangeMe!2026"})
    d = r.json()
    assert d["mfa_required"] and d["dev_code"] and d["access_token"] is None
    bad = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": d["mfa_token"], "code": "000000" if d["dev_code"] != "000000" else "111111"})
    assert bad.json()["error"]["code"] == "OTP_INVALID"
    ok = client.post("/api/v1/auth/mfa/verify", json={"mfa_token": d["mfa_token"], "code": d["dev_code"]})
    assert ok.status_code == 200
    assert "lb_access" in ok.cookies
    me = client.get("/api/v1/auth/me").json()          # cookie auth
    assert "super_admin" in [r["role"] for r in me["roles"]] and "iam:edit" in me["permissions"]


def test_lockout(client):
    make_user("lock@test.ke", "programme_meal_officer")
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"identifier": "lock@test.ke", "password": "wrong"})
    r = client.post("/api/v1/auth/login", json={"identifier": "lock@test.ke", "password": PW})
    assert r.status_code == 423


def test_supplier_registration_flow(client):
    county = str(org_id("MAKUENI"))
    body = {"account_type": "cooperative", "legal_name": "Umoja Farmers Cooperative", "contact_name": "Amina Otieno",
            "phone": "0712 345 678", "county_id": county, "commodities": ["MAIZE-FLOUR", "BEANS"], "members_count": 146,
            "inclusion": {"leadership": "women", "pct_women": 61}, "inclusion_consent": True, "accept_terms": True,
            "password": "weak"}
    assert client.post("/api/v1/auth/register/supplier", json=body).json()["error"]["code"] == "WEAK_PASSWORD"
    body["password"] = PW
    r = client.post("/api/v1/auth/register/supplier", json=body)
    assert r.status_code == 201, r.text
    reg = r.json()
    # can't sign in before verifying phone
    r2 = client.post("/api/v1/auth/login", json={"identifier": "0712345678", "password": PW})
    assert r2.json()["error"]["code"] == "PHONE_NOT_VERIFIED"
    v = client.post("/api/v1/auth/verify-phone", json={"user_id": reg["user_id"], "code": reg["dev_code"]})
    assert v.status_code == 200
    mine = client.get("/api/v1/suppliers/me").json()
    assert mine["status"] == "submitted" and mine["inclusion_verified"] is False
    assert mine["inclusion_claim"]["leadership"] == "women"
    dup = client.post("/api/v1/auth/register/supplier", json=body)
    assert dup.json()["error"]["code"] == "PHONE_IN_USE"


def test_otp_login_and_password_reset(client):
    make_user("otp@test.ke", "school_meals_officer", "MAKUENI-SCH001", phone="+254722000111")
    r = client.post("/api/v1/auth/otp/request", json={"phone": "0722000111"}).json()
    ok = client.post("/api/v1/auth/otp/login", json={"phone": "0722000111", "code": r["dev_code"]})
    assert ok.status_code == 200
    f = client.post("/api/v1/auth/password/forgot", json={"identifier": "otp@test.ke"}).json()
    rs = client.post("/api/v1/auth/password/reset", json={"identifier": "otp@test.ke", "code": f["dev_code"],
                                                         "new_password": "An0therStrongOne"})
    assert rs.status_code == 200
    login(client, "otp@test.ke", "An0therStrongOne")


def test_refresh_rotation(client):
    make_user("rot@test.ke", "programme_meal_officer")
    r = client.post("/api/v1/auth/login", json={"identifier": "rot@test.ke", "password": PW}).json()
    first = r["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert r2.status_code == 200
    again = client.post("/api/v1/auth/refresh", json={"refresh_token": first})   # old token no longer valid
    assert again.status_code == 401
