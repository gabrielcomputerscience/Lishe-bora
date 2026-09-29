"""Phase 4: intake → inspection → stock → dispatch → driver → e-POD → exceptions → traceability."""
import uuid
from datetime import date

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import PurchaseOrder
from tests.conftest import login, org_id

PW = "Demo!2026pass"
A = "/api/v1"


def h(client, who):
    return login(client, f"{who}@demo.lishebora", PW)


def hub():
    return str(org_id("HUB-DEMO-101"))


def make_cleared_batch(client, commodity="MAIZE-FLOUR", qtys=(800, 450), moisture=12.9):
    ag, qi = h(client, "aggregator"), h(client, "inspector")
    ref = uuid.uuid4().hex
    first = None
    for i, q in enumerate(qtys):
        r = client.post(f"{A}/intakes", headers=ag, json={"location_id": hub(), "producer_name": f"Farmer {i}", "producer_gender": "female" if i == 0 else "male",
                                                          "producer_youth": i == 0, "commodity_code": commodity, "quantity": str(q),
                                                          "client_ref": f"{ref}-{i}"})
        assert r.status_code == 201, r.text
        first = first or r.json()
    # offline retry of the same intake is idempotent
    again = client.post(f"{A}/intakes", headers=ag, json={"location_id": hub(), "producer_name": "Farmer 0", "commodity_code": commodity,
                                                          "quantity": str(qtys[0]), "client_ref": f"{ref}-0"}).json()
    assert again["duplicate"] and again["id"] == first["id"]
    bid = first["batch"]["id"]
    b = client.get(f"{A}/batches/{bid}", headers=ag).json()
    assert float(b["intake_qty"]) == sum(qtys) and b["status"] == "open"
    assert client.post(f"{A}/batches/{bid}/request-inspection", headers=ag).json()["status"] == "awaiting_inspection"
    total = sum(qtys)
    r = client.post(f"{A}/batches/{bid}/inspections", headers=qi, json={
        "parameters": {"moisture_pct": moisture}, "visual_checks": {"pests": False, "mould": False}, "result": "accepted",
        "accepted_qty": str(total), "rejected_qty": "0", "grade": "Grade 1", "client_ref": f"{ref}-insp", "captured_offline": True})
    assert r.status_code == 201, r.text
    return bid, b["code"]


def test_intake_inspection_rules(client):
    ag, qi = h(client, "aggregator"), h(client, "inspector")
    # quality inspectors hold agg:create, but SoD-09 blocks them from inspecting a batch they recorded intake for
    r = client.post(f"{A}/intakes", headers=qi, json={"location_id": hub(), "producer_name": "Self Intake", "commodity_code": "BEANS",
                                                      "variety": "own", "quantity": "50"})
    assert r.status_code == 201
    own = r.json()["batch"]["id"]
    client.post(f"{A}/batches/{own}/request-inspection", headers=ag)
    r = client.post(f"{A}/batches/{own}/inspections", headers=qi, json={"result": "accepted", "accepted_qty": "50", "rejected_qty": "0"})
    assert r.status_code == 403 and "segregation" in r.json()["error"]["message"]

    # a failed moisture check cannot be recorded as plain 'accepted'; partial rejection raises an exception case
    r = client.post(f"{A}/intakes", headers=ag, json={"location_id": hub(), "producer_name": "Wet Maize", "commodity_code": "MAIZE-FLOUR",
                                                      "variety": "wet-test", "quantity": "300"})
    bid = r.json()["batch"]["id"]
    client.post(f"{A}/batches/{bid}/request-inspection", headers=ag)
    bad = client.post(f"{A}/batches/{bid}/inspections", headers=qi, json={"parameters": {"moisture_pct": 15.2}, "result": "accepted",
                                                                        "accepted_qty": "300", "rejected_qty": "0"})
    assert bad.json()["error"]["code"] == "QUALITY_FAILED"
    mismatch = client.post(f"{A}/batches/{bid}/inspections", headers=qi, json={"result": "partially_accepted", "accepted_qty": "100",
                                                                             "rejected_qty": "100", "reason": "wet"})
    assert mismatch.status_code == 422
    ok = client.post(f"{A}/batches/{bid}/inspections", headers=qi, json={"parameters": {"moisture_pct": 15.2}, "result": "partially_accepted",
                                                                       "accepted_qty": "200", "rejected_qty": "100", "reason": "Top sacks wet",
                                                                       "corrective_action": "Dry to below 13.5% and re-submit"})
    assert ok.status_code == 201, ok.text
    b = client.get(f"{A}/batches/{bid}", headers=ag).json()
    assert b["status"] == "cleared" and float(b["on_hand"]) == 200
    cases = client.get(f"{A}/exceptions", headers=h(client, "procurement")).json()
    assert any(c["category"] == "quality_rejection" and c["entity_ref"] == b["code"] for c in cases)
    # supplier was told
    assert any("Inspection result" in n["title"] for n in client.get(f"{A}/notifications", headers=ag).json()["items"])


def test_dispatch_pod_and_trace(client):
    bid, code = make_cleared_batch(client)
    lg, dr, s1, s2 = h(client, "logistics"), h(client, "driver"), h(client, "school.admin"), h(client, "school2.admin")
    data = client.get(f"{A}/dispatch/orders", headers=lg).json()
    po = next(o for o in data["orders"] if o["reference"] == "PO-DEMO-0001")
    maize = next(ln for ln in po["lines"] if ln["commodity_code"] == "MAIZE-FLOUR")
    assert any(r["batch_id"] == bid for r in data["stock"])
    sch = {s["name"]: s for s in maize["schools"]}
    a, b = sch["Kalulini"], sch["Muatini"]
    drivers = client.get(f"{A}/dispatch/drivers", headers=lg).json()
    body = {"po_id": po["id"], "source_location_id": hub(), "vehicle": "kcx 123a", "driver_user_id": drivers[0]["id"],
            "planned_date": str(date.today()), "lines": [
                {"po_line_id": maize["po_line_id"], "school_id": a["school_id"], "batch_id": bid, "quantity": "700"},
                {"po_line_id": maize["po_line_id"], "school_id": b["school_id"], "batch_id": bid, "quantity": "500"}]}
    over = {**body, "lines": [{**body["lines"][0], "quantity": "701"}]}
    assert client.post(f"{A}/dispatches", headers=lg, json=over).json()["error"]["code"] == "OVER_ORDER"
    d = client.post(f"{A}/dispatches", headers=lg, json=body)
    assert d.status_code == 201, d.text
    d = d.json()
    # schools cannot confirm before dispatch
    first_line = d["stops"][0]["lines"][0]
    assert client.post(f"{A}/dispatches/{d['id']}/pod", headers=s1, json={"school_id": a["school_id"], "receiver_name": "Head teacher",
                                                                         "lines": [{"line_id": first_line["id"], "accepted_qty": "1"}]}).status_code == 409
    d = client.post(f"{A}/dispatches/{d['id']}/dispatch", headers=lg).json()
    assert d["status"] == "dispatched"
    bal = client.get(f"{A}/batches/{bid}", headers=h(client, "aggregator")).json()
    assert float(bal["on_hand"]) == 1250 - 1200
    # driver sees and moves only their own trip
    assert any(x["id"] == d["id"] for x in client.get(f"{A}/dispatches", headers=dr).json())
    d = client.post(f"{A}/dispatches/{d['id']}/milestones", headers=dr, json={"status": "in_transit", "lat": -1.2921, "lng": 36.8219}).json()
    assert d["status"] == "in_transit"
    # school 1: full acceptance, with a signature
    stop_a = next(s for s in d["stops"] if s["school_id"] == a["school_id"])
    sig = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    # school 2 cannot confirm school 1's stop
    assert client.post(f"{A}/dispatches/{d['id']}/pod", headers=s2, json={"school_id": a["school_id"], "receiver_name": "Wrong school",
                                                                         "lines": [{"line_id": stop_a["lines"][0]["id"], "accepted_qty": "700"}]}).status_code == 403
    r = client.post(f"{A}/dispatches/{d['id']}/pod", headers=s1, json={
        "school_id": a["school_id"], "receiver_name": "Mary Head Teacher", "signature": sig, "client_ref": "pod-a-1", "captured_offline": True,
        "lines": [{"line_id": stop_a["lines"][0]["id"], "accepted_qty": "700"}]})
    assert r.status_code == 201, r.text
    assert client.post(f"{A}/dispatches/{d['id']}/pod", headers=s1, json={
        "school_id": a["school_id"], "receiver_name": "Mary Head Teacher", "client_ref": "pod-a-1",
        "lines": [{"line_id": stop_a["lines"][0]["id"], "accepted_qty": "700"}]}).json()["duplicate"]
    # school 2: 40 kg rejected (wet), 10 kg short
    stop_b = next(s for s in d["stops"] if s["school_id"] == b["school_id"])
    r = client.post(f"{A}/dispatches/{d['id']}/pod", headers=s2, json={
        "school_id": b["school_id"], "receiver_name": "Deputy", "condition": "wet",
        "lines": [{"line_id": stop_b["lines"][0]["id"], "accepted_qty": "450", "rejected_qty": "40", "rejection_reason": "Wet sacks"}]})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "closed"
    with SessionLocal() as db:
        po_row = db.scalar(select(PurchaseOrder).where(PurchaseOrder.reference == "PO-DEMO-0001"))
        assert po_row.status.value == "partially_fulfilled"
    cats = {c["category"] for c in client.get(f"{A}/exceptions", headers=h(client, "procurement")).json() if c["entity_ref"] == d["reference"]}
    assert {"rejected_goods", "short_delivery"} <= cats
    # rejected goods went back to hub stock; school stock shows the receipt
    assert float(client.get(f"{A}/batches/{bid}", headers=h(client, "aggregator")).json()["on_hand"]) == 50 + 40
    school_bal = client.get(f"{A}/inventory/balances", headers=h(client, "meals.officer")).json()
    assert any(r["batch_code"] == code and float(r["on_hand"]) == 700 for r in school_bal)
    # remaining to send to school 2 is 50 (500 - 450 accepted)
    data = client.get(f"{A}/dispatch/orders", headers=lg).json()
    po = next(o for o in data["orders"] if o["reference"] == "PO-DEMO-0001")
    mz = next(ln for ln in po["lines"] if ln["commodity_code"] == "MAIZE-FLOUR")
    assert float(next(s for s in mz["schools"] if s["school_id"] == b["school_id"])["remaining"]) == 50
    # traceability: farmer → school
    t = client.get(f"{A}/trace/{code}", headers=h(client, "procurement")).json()
    assert t["producer_summary"]["women"] >= 1 and len(t["deliveries"]) == 2 and t["deliveries"][0]["school"]
    # school meals officer records consumption
    r = client.post(f"{A}/inventory/consumption", headers=h(client, "meals.officer"), json={
        "location_id": a["school_id"], "commodity_code": "MAIZE-FLOUR", "quantity": "90", "meals_served": 600})
    assert r.status_code == 201, r.text
    # resolve an exception
    ca = h(client, "county.admin")
    case = next(c for c in client.get(f"{A}/exceptions", headers=ca).json() if c["entity_ref"] == d["reference"])
    assert client.post(f"{A}/exceptions/{case['id']}/progress", headers=h(client, "procurement"),
                       json={"text": "Supplier to replace 40 kg"}).json()["status"] == "in_progress"
    assert client.post(f"{A}/exceptions/{case['id']}/resolve", headers=ca, json={"text": "Replaced"}).json()["status"] == "resolved"


def test_adjustment_and_count_need_approval(client):
    bid, code = make_cleared_batch(client, commodity="BEANS", qtys=(120,), moisture=12)
    ag, wh = h(client, "aggregator"), h(client, "warehouse.supervisor")
    r = client.post(f"{A}/inventory/adjustments", headers=ag, json={"location_id": hub(), "batch_id": bid, "quantity": "-5", "type": "waste",
                                                                    "reason": "Torn sack, spilled"})
    assert r.status_code == 201, r.text
    w = r.json()["workflow"]["id"]
    assert float(client.get(f"{A}/batches/{bid}", headers=ag).json()["on_hand"]) == 120   # not posted yet
    assert client.post(f"{A}/workflow/{w}/act", headers=ag, json={"action": "approve"}).status_code == 403
    assert client.post(f"{A}/workflow/{w}/act", headers=wh, json={"action": "approve"}).status_code == 200
    assert float(client.get(f"{A}/batches/{bid}", headers=ag).json()["on_hand"]) == 115
    # count with variance → approval → adjustment posted
    c = client.post(f"{A}/inventory/counts", headers=ag, json={"location_id": hub(), "lines": [
        {"batch_id": bid, "commodity_code": "BEANS", "counted_qty": "110"}]}).json()
    assert c["lines"][0]["variance"] == "-5.00" and c["workflow"]
    client.post(f"{A}/workflow/{c['workflow']['id']}/act", headers=wh, json={"action": "approve"})
    assert float(client.get(f"{A}/batches/{bid}", headers=ag).json()["on_hand"]) == 110
    # transfer to the county store
    r = client.post(f"{A}/inventory/transfers", headers=ag, json={"from_location_id": hub(), "to_location_id": str(org_id("WH-DEMO-A1")),
                                                                  "batch_id": bid, "quantity": "200"})
    assert r.json()["error"]["code"] == "INSUFFICIENT_STOCK"
