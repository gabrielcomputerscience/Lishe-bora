from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import AcademicTerm, Menu
from tests.conftest import login, make_user, org_id

DEMO_PW = "Demo!2026pass"


def ids():
    with SessionLocal() as db:
        t3 = db.scalar(select(AcademicTerm.id).where(AcademicTerm.year == 2026, AcademicTerm.term_no == 3))
        menu = db.scalar(select(Menu.id).where(Menu.name == "Standard 5-day menu (demo)"))
    return t3, menu


def demand_body(school, term, menu, enrolment=612, stock=None):
    return {"school_id": str(school), "term_id": str(term), "menu_id": str(menu), "enrolment": enrolment,
            "attendance_pct": 95, "feeding_days": 45, "wastage_pct": 3, "stock": stock or []}


def test_demand_calculation_and_validation(client):
    term, menu = ids()
    h = login(client, "meals.officer@demo.lishebora", DEMO_PW)
    r = client.post("/api/v1/demands", headers=h, json=demand_body(org_id("MAKUENI-SCH001"), term, menu,
                                                                   stock=[{"commodity": "MAIZE-FLOUR", "qty": 400}]))
    assert r.status_code == 201, r.text
    d = r.json()
    maize = next(ln for ln in d["lines"] if ln["commodity"] == "MAIZE-FLOUR")
    # 612 × 0.95 × (45/5) × 450 g / 1000 × 1.03 = 2425.31 kg gross; minus 400 kg stock
    assert Decimal(str(maize["gross_qty"])) == Decimal("2425.31")
    assert Decimal(str(maize["net_qty"])) == Decimal("2025.31")
    assert d["nutrition"]["group_count"] >= 5 and d["nutrition"]["meets_minimum"]
    assert not [f for f in d["flags"] if f["severity"] == "error"]
    # feeding days above the term calendar → blocking error
    bad = dict(demand_body(org_id("MAKUENI-SCH001"), term, menu), feeding_days=90)
    r2 = client.put(f"/api/v1/demands/{d['id']}", headers=h, json=bad).json()
    assert any(f["code"] == "FEEDING_DAYS" for f in r2["flags"])
    assert client.post(f"/api/v1/demands/{d['id']}/submit", headers=h).json()["error"]["code"] == "DEMAND_INVALID"
    client.put(f"/api/v1/demands/{d['id']}", headers=h, json=demand_body(org_id("MAKUENI-SCH001"), term, menu,
                                                                          stock=[{"commodity": "MAIZE-FLOUR", "qty": 400}]))


def test_demand_approval_and_sod(client):
    term, menu = ids()
    mh = login(client, "meals.officer@demo.lishebora", DEMO_PW)
    d = client.get("/api/v1/demands", headers=mh).json()[0]
    s = client.post(f"/api/v1/demands/{d['id']}/submit", headers=mh).json()
    assert s["status"] == "submitted"
    wid = s["workflow"]["id"]
    # initiator cannot approve own submission
    assert client.post(f"/api/v1/workflow/{wid}/act", headers=mh, json={"action": "approve"}).json()["error"]["code"] == "WORKFLOW_FORBIDDEN"
    ah = login(client, "school.admin@demo.lishebora", DEMO_PW)
    inbox = client.get("/api/v1/workflow/inbox", headers=ah).json()["waiting_for_me"]
    assert any(i["id"] == wid for i in inbox)
    client.post(f"/api/v1/workflow/{wid}/act", headers=ah, json={"action": "approve"})
    assert client.get(f"/api/v1/demands/{d['id']}", headers=ah).json()["status"] == "validated"
    client.post(f"/api/v1/workflow/{wid}/act", headers=ah, json={"action": "approve"})
    assert client.get(f"/api/v1/demands/{d['id']}", headers=ah).json()["status"] == "approved"
    # locked once approved
    r = client.put(f"/api/v1/demands/{d['id']}", headers=mh, json=demand_body(org_id("MAKUENI-SCH001"), term, menu))
    assert r.json()["error"]["code"] == "LOCKED"


def test_scope_other_county_cannot_see(client):
    make_user("cpob@test.ke", "county_procurement_officer", "EMBU")
    h = login(client, "cpob@test.ke")
    assert client.get("/api/v1/demands", headers=h).json() == []


def test_plan_budget_exception_and_commitment(client):
    term, menu = ids()
    # second school demand, approved by the county administrator (also holds dem:approve/verify? verify via CPO)
    mh = login(client, "meals.officer@demo.lishebora", DEMO_PW)
    make_user("meals2@test.ke", "school_meals_officer", "MAKUENI-SCH002")
    m2 = login(client, "meals2@test.ke")
    d2 = client.post("/api/v1/demands", headers=m2, json=demand_body(org_id("MAKUENI-SCH002"), term, menu, 480)).json()
    w2 = client.post(f"/api/v1/demands/{d2['id']}/submit", headers=m2).json()["workflow"]["id"]
    ph = login(client, "procurement@demo.lishebora", DEMO_PW)     # dem:verify
    client.post(f"/api/v1/workflow/{w2}/act", headers=ph, json={"action": "approve"})
    ch = login(client, "county.admin@demo.lishebora", DEMO_PW)    # dem:approve
    client.post(f"/api/v1/workflow/{w2}/act", headers=ch, json={"action": "approve"})

    county = str(org_id("MAKUENI"))
    prev = client.post("/api/v1/plans/preview", headers=ph, json={"county_id": county, "term_id": str(term)}).json()
    assert prev["demand_count"] == 2 and prev["lines"]
    plan = client.post("/api/v1/plans", headers=ph, json={"county_id": county, "term_id": str(term)}).json()
    assert plan["demand_count"] == 2 and plan["unpriced_lines"] == 0
    est = Decimal(plan["estimated_value"])
    # finance creates a deliberately small budget line → submission blocked
    fh = login(client, "finance@demo.lishebora", DEMO_PW)
    fs = client.get("/api/v1/funding-sources", headers=fh).json()[0]["id"]
    small = client.post("/api/v1/budget-lines", headers=fh, json={
        "code": "TEST-SMALL", "name": "Small line", "funding_source_id": fs, "org_id": county,
        "period_start": "2026-08-24", "period_end": "2026-10-30", "approved_amount": str((est / 2).quantize(Decimal("1")))}).json()
    client.put(f"/api/v1/plans/{plan['id']}", headers=ph, json={"budget_line_id": small["id"]})
    r = client.post(f"/api/v1/plans/{plan['id']}/submit", headers=ph).json()
    assert r["error"]["code"] == "BUDGET_EXCEEDED"
    # exception: finance requests, county admin approves
    exc = client.post("/api/v1/budget-exceptions", headers=fh, json={
        "plan_id": plan["id"], "justification": "Enrolment rose after the budget was set; top-up requested from the grant."}).json()
    einst = next(i for i in client.get("/api/v1/workflow/inbox", headers=ch).json()["waiting_for_me"] if i["entity_id"] == exc["id"])
    client.post(f"/api/v1/workflow/{einst['id']}/act", headers=ch, json={"action": "approve", "note": "Approved"})
    sub = client.post(f"/api/v1/plans/{plan['id']}/submit", headers=ph).json()
    assert sub["status"] == "submitted"
    wid = sub["workflow"]["id"]
    # county admin cannot do the finance step; CPO (initiator) cannot approve
    assert client.post(f"/api/v1/workflow/{wid}/act", headers=ch, json={"action": "approve"}).status_code == 403
    assert client.post(f"/api/v1/workflow/{wid}/act", headers=ph, json={"action": "approve"}).status_code == 403
    client.post(f"/api/v1/workflow/{wid}/act", headers=fh, json={"action": "approve"})
    done = client.post(f"/api/v1/workflow/{wid}/act", headers=ch, json={"action": "approve"}).json()
    assert done["status"] == "approved"
    final = client.get(f"/api/v1/plans/{plan['id']}", headers=ch).json()
    assert final["status"] == "approved"
    line = client.get(f"/api/v1/budget-lines/{small['id']}", headers=fh).json()
    assert Decimal(line["committed"]) == est and Decimal(line["available"]) < 0
    assert line["alerts"][0]["code"] == "OVER_COMMITTED"


def test_return_requires_reason(client):
    term, menu = ids()
    make_user("nut2@test.ke", "nutrition_officer", "MAKUENI")
    h = login(client, "nut2@test.ke")
    m = client.post("/api/v1/menus", headers=h, json={"name": "Test menu", "days": [
        {"label": "Mon", "dish": "Rice", "components": [{"commodity": "RICE-WHITE", "portion_g": 120}]}]}).json()
    assert not m["summary"]["meets_minimum"]
    s = client.post(f"/api/v1/menus/{m['id']}/submit", headers=h).json()
    ph = login(client, "procurement@demo.lishebora", DEMO_PW)
    wid = s["workflow"]["id"]
    assert client.post(f"/api/v1/workflow/{wid}/act", headers=ph, json={"action": "return"}).status_code == 422
    client.post(f"/api/v1/workflow/{wid}/act", headers=ph, json={"action": "return", "note": "Add legumes and vegetables"})
    menus = {x["id"]: x for x in client.get("/api/v1/menus", headers=h).json()}
    assert menus[m["id"]]["status"] == "draft"
