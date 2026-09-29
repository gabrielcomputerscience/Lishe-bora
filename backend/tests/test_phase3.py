from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import AcademicTerm, Menu, ProcurementEvent
from tests.conftest import login, org_id

PW = "Demo!2026pass"


def approved_plan(client):
    with SessionLocal() as db:
        t2 = db.scalar(select(AcademicTerm.id).where(AcademicTerm.year == 2026, AcademicTerm.term_no == 2))
        menu = db.scalar(select(Menu.id).where(Menu.name == "Standard 5-day menu (demo)"))
    mh, sa = login(client, "meals.officer@demo.lishebora", PW), login(client, "school.admin@demo.lishebora", PW)
    d = client.post("/api/v1/demands", headers=mh, json={"school_id": str(org_id("MAKUENI-SCH001")), "term_id": str(t2),
                                                         "menu_id": str(menu), "enrolment": 500, "feeding_days": 60}).json()
    w = client.post(f"/api/v1/demands/{d['id']}/submit", headers=mh).json()["workflow"]["id"]
    for _ in range(2):
        client.post(f"/api/v1/workflow/{w}/act", headers=sa, json={"action": "approve"})
    ph, fh, ch = (login(client, e, PW) for e in ("procurement@demo.lishebora", "finance@demo.lishebora", "county.admin@demo.lishebora"))
    county = str(org_id("MAKUENI"))
    fs = client.get("/api/v1/funding-sources", headers=fh).json()[0]["id"]
    bl = client.post("/api/v1/budget-lines", headers=fh, json={"code": "T2-BIG", "name": "Term 2 line", "funding_source_id": fs,
                                                              "org_id": county, "period_start": "2026-04-27", "period_end": "2026-07-31",
                                                              "approved_amount": "5000000"}).json()
    plan = client.post("/api/v1/plans", headers=ph, json={"county_id": county, "term_id": str(t2), "group_by": "county"}).json()
    client.put(f"/api/v1/plans/{plan['id']}", headers=ph, json={"budget_line_id": bl["id"]})
    w = client.post(f"/api/v1/plans/{plan['id']}/submit", headers=ph).json()["workflow"]["id"]
    client.post(f"/api/v1/workflow/{w}/act", headers=fh, json={"action": "approve"})
    client.post(f"/api/v1/workflow/{w}/act", headers=ch, json={"action": "approve"})
    return plan, bl


def test_full_procurement_cycle(client):
    plan, bl = approved_plan(client)
    ph = login(client, "procurement@demo.lishebora", PW)
    closes = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    ev = client.post("/api/v1/procurement-events/from-plan", headers=ph, json={"plan_id": plan["id"], "closes_at": closes}).json()
    assert ev["status"] == "draft" and len(ev["lots"]) == len(plan["lines"])
    # weights must add up
    bad = client.put(f"/api/v1/procurement-events/{ev['id']}", headers=ph, json={"technical_weight": 70})
    assert bad.json()["error"]["code"] == "WEIGHTS"
    w = client.post(f"/api/v1/procurement-events/{ev['id']}/submit", headers=ph).json()["workflow"]["id"]
    assert client.post(f"/api/v1/workflow/{w}/act", headers=ph, json={"action": "approve"}).status_code == 403  # own submission
    ah = login(client, "approver@demo.lishebora", PW)
    client.post(f"/api/v1/workflow/{w}/act", headers=ah, json={"action": "approve"})
    assert client.get(f"/api/v1/procurement-events/{ev['id']}", headers=ph).json()["status"] == "open"

    s1, s2 = login(client, "supplier1@demo.lishebora", PW), login(client, "supplier2@demo.lishebora", PW)
    assert any("New opportunity" in n["title"] for n in client.get("/api/v1/notifications", headers=s1).json()["items"])
    opp = client.get(f"/api/v1/supplier/opportunities/{ev['id']}", headers=s1).json()
    assert opp["eligible"] and "estimated_value" not in opp
    lots = opp["lots"]
    mk = lambda f: {"lines": [{"lot_id": lt["id"], "unit_price": str(round(float(ln["unit_price"] or 50) * f, 2)),  # noqa: E731
                               "quantity": str(lt["quantity"])} for lt, ln in zip(lots, plan["lines"])],
                    "delivery_plan": "Two deliveries per month"}
    b1 = client.put(f"/api/v1/supplier/opportunities/{ev['id']}/bid", headers=s1, json=mk(1.0)).json()
    client.post(f"/api/v1/supplier/opportunities/{ev['id']}/bid/submit", headers=s1)
    client.put(f"/api/v1/supplier/opportunities/{ev['id']}/bid", headers=s2, json=mk(0.9))
    r = client.post(f"/api/v1/supplier/opportunities/{ev['id']}/bid/submit", headers=s2).json()
    assert r["status"] == "submitted" and r["receipt"]
    # sealed: officers see metadata only
    sealed = client.get(f"/api/v1/procurement-events/{ev['id']}/bids", headers=ph).json()
    assert sealed["opened"] is False and all(b["contents"] is None for b in sealed["bids"]) and len(sealed["bids"]) == 2
    assert client.post(f"/api/v1/procurement-events/{ev['id']}/open", headers=ph).json()["error"]["code"] == "NOT_CLOSED"
    # clarification: supplier asks, officer answers
    client.post(f"/api/v1/supplier/opportunities/{ev['id']}/questions", headers=s2, json={"question": "Can we deliver in two batches?"})
    q = client.get(f"/api/v1/procurement-events/{ev['id']}/clarifications", headers=ph).json()[0]
    client.post(f"/api/v1/procurement-events/clarifications/{q['id']}/answer", headers=ph, json={"answer": "Yes, two batches are fine."})
    assert any(c["answer"] for c in client.get(f"/api/v1/supplier/opportunities/{ev['id']}", headers=s1).json()["clarifications"])

    # time passes → automatic closing; late bid blocked
    with SessionLocal() as db:
        db.execute(update(ProcurementEvent).where(ProcurementEvent.reference == ev["reference"])
                   .values(closes_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()
    late = client.put(f"/api/v1/supplier/opportunities/{ev['id']}/bid", headers=s1, json=mk(0.5))
    assert late.json()["error"]["code"] == "BIDDING_CLOSED"
    reg = client.post(f"/api/v1/procurement-events/{ev['id']}/open", headers=ph).json()
    assert len(reg["register"]) == 2

    # evaluation panel
    ev_detail = client.get(f"/api/v1/procurement-events/{ev['id']}/evaluators", headers=ph).json()
    cands = {c["name"]: c["id"] for c in ev_detail["candidates"]}
    me = client.get("/api/v1/auth/me", headers=ph).json()["id"]
    assert client.post(f"/api/v1/procurement-events/{ev['id']}/evaluators", headers=ph,
                       json={"user_ids": [me]}).json()["error"]["code"] == "SOD_CONFLICT"
    client.post(f"/api/v1/procurement-events/{ev['id']}/evaluators", headers=ph,
                json={"user_ids": [cands["Evaluator One (demo)"], cands["Evaluator Two (demo)"]]})
    e1, e2 = login(client, "evaluator1@demo.lishebora", PW), login(client, "evaluator2@demo.lishebora", PW)
    assert client.get(f"/api/v1/evaluations/{ev['id']}", headers=e1).json()["bids"] is None       # COI first
    assert client.put(f"/api/v1/evaluations/{ev['id']}/scores", headers=e1, json={"scores": {}}).json()["error"]["code"] == "COI_REQUIRED"
    client.post(f"/api/v1/evaluations/{ev['id']}/coi", headers=e1, json={"has_conflict": False, "statement": "I have no interest in any bidder."})
    client.post(f"/api/v1/evaluations/{ev['id']}/coi", headers=e2, json={"has_conflict": True, "statement": "My cousin owns Tumaini Grain Traders."})
    ws = client.get(f"/api/v1/evaluations/{ev['id']}", headers=e1).json()
    assert len(ws["bids"]) == 2
    inc = {b["supplier"]: b["auto_scores"]["inclusion"] for b in ws["bids"]}
    assert inc["Umoja Farmers Cooperative (demo)"] == 5 and inc["Tumaini Grain Traders (demo)"] == 0
    scores = {b["id"]: {"technical": 18, "capacity": 13, "quality": 9, "local": 8} for b in ws["bids"]}
    assert client.put(f"/api/v1/evaluations/{ev['id']}/scores", headers=e1,
                      json={"scores": {k: {**v, "quality": 99} for k, v in scores.items()}}).status_code == 422
    client.put(f"/api/v1/evaluations/{ev['id']}/scores", headers=e1, json={"scores": scores})
    client.post(f"/api/v1/evaluations/{ev['id']}/submit", headers=e1)
    res = client.post(f"/api/v1/procurement-events/{ev['id']}/consolidate", headers=ph).json()["results"]
    assert res["evaluators"] == ["Evaluator One (demo)"]          # conflicted evaluator excluded
    lot0 = res["lots"][0]
    top = lot0["bids"][0]
    # equal technical except inclusion (+5 for Umoja) vs 10% cheaper price (+4 financial for Tumaini): Umoja wins by 1
    assert top["supplier"] == "Umoja Farmers Cooperative (demo)"
    assert lot0["bids"][1]["financial"] == 40.0

    # award: finance commitment check, approving officer approves
    w = client.post(f"/api/v1/procurement-events/{ev['id']}/recommend", headers=ph).json()["workflow"]["id"]
    fh = login(client, "finance@demo.lishebora", PW)
    assert client.post(f"/api/v1/workflow/{w}/act", headers=ah, json={"action": "approve"}).status_code == 403  # wrong stage perm
    client.post(f"/api/v1/workflow/{w}/act", headers=fh, json={"action": "approve"})
    done = client.post(f"/api/v1/workflow/{w}/act", headers=ah, json={"action": "approve"}).json()
    assert done["status"] == "approved"
    final = client.get(f"/api/v1/procurement-events/{ev['id']}", headers=ph).json()
    assert final["status"] == "awarded" and "Umoja" in final["awarded_to"]
    # budget: plan earmark released, contract committed for award value
    line = client.get(f"/api/v1/budget-lines/{bl['id']}", headers=fh).json()
    held = [c for c in line["commitments"] if c["status"] == "held"]
    assert [c["source"] for c in held] == ["contract"]
    assert Decimal(str(line["committed"])) == Decimal(str(final["awarded_value"]))
    # supplier sees contract + PO and acknowledges; loser notified
    orders = client.get("/api/v1/supplier/orders", headers=s1).json()
    assert orders["contracts"][0]["kind"] == "purchase" and orders["orders"][0]["status"] == "issued"
    ack = client.post(f"/api/v1/supplier/orders/{orders['orders'][0]['id']}/acknowledge", headers=s1).json()
    assert ack["status"] == "acknowledged"
    assert any("not successful" in n["body"] for n in client.get("/api/v1/notifications", headers=s2).json()["items"])
    # call-off only for frameworks
    cid = orders["contracts"][0]["id"]
    r = client.post(f"/api/v1/contracts/{cid}/call-offs", headers=ph, json={"lines": [{"contract_line_id": orders["contracts"][0]["lines"][0]["id"], "quantity": "1"}]})
    assert r.json()["error"]["code"] == "NOT_FRAMEWORK"
    # public award notice
    pub = client.get("/api/v1/public/opportunities").json()
    assert any(a["reference"] == ev["reference"] for a in pub["awards"])


def test_framework_call_off_balance(client):
    from datetime import date, timedelta as td
    from app.models import Contract, ContractKind, ContractLine, ProcurementLot, Supplier
    with SessionLocal() as db:
        ev = db.scalar(select(ProcurementEvent).where(ProcurementEvent.status == "awarded"))
        lot = db.scalar(select(ProcurementLot).where(ProcurementLot.event_id == ev.id))
        sup = db.scalar(select(Supplier).where(Supplier.legal_name == "Tumaini Grain Traders (demo)"))
        c = Contract(reference="CON-FWK-TEST", event_id=ev.id, supplier_id=sup.id, county_id=ev.county_id, kind=ContractKind.framework,
                     value=Decimal("10000"), starts_on=date.today(), ends_on=date.today() + td(days=60))
        c.lines.append(ContractLine(lot_id=lot.id, commodity_code=lot.commodity_code, unit="kg", quantity=Decimal("100"),
                                    unit_price=Decimal("100"), quantity_ordered=Decimal("0")))
        db.add(c)
        db.commit()
        cid, lid = str(c.id), str(c.lines[0].id)
    ph = login(client, "procurement@demo.lishebora", PW)
    ok = client.post(f"/api/v1/contracts/{cid}/call-offs", headers=ph, json={"lines": [{"contract_line_id": lid, "quantity": "60"}]})
    assert ok.status_code == 201 and Decimal(str(ok.json()["total"])) == Decimal("6000")
    over = client.post(f"/api/v1/contracts/{cid}/call-offs", headers=ph, json={"lines": [{"contract_line_id": lid, "quantity": "50"}]})
    assert over.json()["error"]["code"] == "CONTRACT_BALANCE"
    last = client.post(f"/api/v1/contracts/{cid}/call-offs", headers=ph, json={"lines": [{"contract_line_id": lid, "quantity": "40"}]})
    assert last.status_code == 201
    detail = client.get(f"/api/v1/contracts/{cid}", headers=ph).json()
    assert detail["status"] == "completed" and len(detail["orders"]) == 2
