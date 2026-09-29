"""Phase 5: three-way match, invoice approval, payment SoD, budget movement, complaints, scorecards, MEAL, exports."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, update

from app.core.database import SessionLocal
from app.models import BudgetLine, Invoice
from app.services import budget
from tests.conftest import org_id
from tests.test_phase4 import A, h, hub, make_cleared_batch


def deliver_beans(client):
    bid, _ = make_cleared_batch(client, commodity="BEANS", qtys=(200, 100), moisture=12)
    lg = h(client, "logistics")
    po = next(o for o in client.get(f"{A}/dispatch/orders", headers=lg).json()["orders"] if o["reference"] == "PO-DEMO-0001")
    beans = next(ln for ln in po["lines"] if ln["commodity_code"] == "BEANS")
    lines = [{"po_line_id": beans["po_line_id"], "school_id": s["school_id"], "batch_id": bid, "quantity": str(s["remaining"])}
             for s in beans["schools"]]
    d = client.post(f"{A}/dispatches", headers=lg, json={"po_id": po["id"], "source_location_id": hub(), "vehicle": "KDA 1B",
                                                         "planned_date": str(date.today()), "lines": lines})
    assert d.status_code == 201, d.text
    d = client.post(f"{A}/dispatches/{d.json()['id']}/dispatch", headers=lg).json()
    for who, code in (("school.admin", "MAKUENI-SCH001"), ("school2.admin", "MAKUENI-SCH002")):
        stop = next(s for s in d["stops"] if s["school_id"] == str(org_id(code)))
        r = client.post(f"{A}/dispatches/{d['id']}/pod", headers=h(client, who), json={
            "school_id": stop["school_id"], "receiver_name": "Head teacher",
            "lines": [{"line_id": ln["id"], "accepted_qty": str(ln["quantity"])} for ln in stop["lines"]]})
        assert r.status_code == 201, r.text
    return po["id"], beans["po_line_id"]


def budget_status():
    with SessionLocal() as db:
        return budget.status(db, db.scalar(select(BudgetLine).where(BudgetLine.code == "DEMO-A-T3")))


def test_invoice_match_approval_and_payment(client):
    po_id, line = deliver_beans(client)
    ag = h(client, "aggregator")
    bill = next(o for o in client.get(f"{A}/invoices/billable", headers=ag).json() if o["id"] == po_id)
    beans = next(ln for ln in bill["lines"] if ln["po_line_id"] == line)
    assert float(beans["billable_qty"]) == 300
    base = {"po_id": po_id, "supplier_invoice_no": "UMJ-001", "invoice_date": str(date.today())}
    over = client.post(f"{A}/invoices", headers=ag, json={**base, "lines": [{"po_line_id": line, "quantity": "301"}]})
    assert over.json()["error"]["code"] == "MATCH_FAILED"
    pricey = client.post(f"{A}/invoices", headers=ag, json={**base, "lines": [{"po_line_id": line, "quantity": "300", "unit_price": "131"}]})
    assert pricey.json()["error"]["code"] == "MATCH_FAILED"
    # a farmer-group account can view but not submit invoices (matrix: fin V)
    assert client.post(f"{A}/invoices", headers=h(client, "supplier1"), json={**base, "lines": [{"po_line_id": line, "quantity": "1"}]}).status_code == 403
    before = budget_status()
    r = client.post(f"{A}/invoices", headers=ag, json={**base, "lines": [{"po_line_id": line, "quantity": "300"}]})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert Decimal(inv["total"]) == Decimal("39000.00") and inv["match"]["result"] == "matched"
    assert client.post(f"{A}/invoices", headers=ag, json={**base, "supplier_invoice_no": "umj-001",
                                                          "lines": [{"po_line_id": line, "quantity": "1"}]}).json()["error"]["code"] == "DUPLICATE_INVOICE"
    w = inv["workflow"]["id"]
    acc, fin, pay = h(client, "accounts"), h(client, "finance"), h(client, "payments")
    assert client.post(f"{A}/workflow/{w}/act", headers=ag, json={"action": "approve"}).status_code == 403
    assert client.post(f"{A}/workflow/{w}/act", headers=acc, json={"action": "approve"}).status_code == 200
    assert client.get(f"{A}/invoices/{inv['id']}", headers=acc).json()["status"] == "verified"
    assert client.post(f"{A}/workflow/{w}/act", headers=acc, json={"action": "approve"}).status_code == 403   # SoD: one step each
    assert client.post(f"{A}/workflow/{w}/act", headers=fin, json={"action": "approve"}).status_code == 200
    mid = budget_status()
    assert mid["invoiced"] - before["invoiced"] == Decimal("39000") and before["committed"] - mid["committed"] == Decimal("39000")
    # verifier cannot pay; payer can
    got = client.get(f"{A}/invoices/{inv['id']}", headers=acc).json()
    assert got["status"] == "approved" and got["can_pay"] is False
    # overdue approved invoice → late-payment exception
    with SessionLocal() as db:
        db.execute(update(Invoice).where(Invoice.reference == inv["reference"]).values(approved_at=datetime.now(timezone.utc) - timedelta(days=40)))
        db.commit()
    client.get(f"{A}/meal/dashboard", headers=h(client, "meal"))
    assert any(c["category"] == "late_payment" and c["entity_ref"] == inv["reference"]
               for c in client.get(f"{A}/exceptions", headers=h(client, "county.admin")).json())
    pbody = {"amount": "20000", "method": "mpesa", "transaction_ref": "QKX12345", "paid_on": str(date.today())}
    assert client.post(f"{A}/invoices/{inv['id']}/payments", headers=acc, json=pbody).status_code == 403
    r = client.post(f"{A}/invoices/{inv['id']}/payments", headers=pay, json=pbody)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "partially_paid"
    assert client.post(f"{A}/invoices/{inv['id']}/payments", headers=pay, json={**pbody, "amount": "1"}).json()["error"]["code"] == "DUPLICATE_PAYMENT"
    assert client.post(f"{A}/invoices/{inv['id']}/payments", headers=pay, json={**pbody, "transaction_ref": "X2", "amount": "19001"}).status_code == 422
    r = client.post(f"{A}/invoices/{inv['id']}/payments", headers=pay, json={**pbody, "transaction_ref": "QKX12399", "amount": "19000"}).json()
    assert r["status"] == "paid" and Decimal(r["balance"]) == 0 and len(r["payments"]) == 2
    after = budget_status()
    assert after["paid"] - mid["paid"] == Decimal("39000") and after["invoiced"] == before["invoiced"]
    late = [c for c in client.get(f"{A}/exceptions?status=resolved", headers=h(client, "county.admin")).json() if c["entity_ref"] == inv["reference"]]
    assert late and late[0]["status"] == "resolved"
    assert any("Payment sent" in n["title"] for n in client.get(f"{A}/notifications", headers=ag).json()["items"])
    # supplier sees its invoices and payments, not others'
    assert any(i["id"] == inv["id"] for i in client.get(f"{A}/invoices", headers=h(client, "supplier1")).json())
    assert not client.get(f"{A}/invoices", headers=h(client, "supplier2")).json()
    # budget line and scorecard
    cards = client.get(f"{A}/performance/suppliers", headers=h(client, "procurement")).json()
    umoja = next(c for c in cards if c["supplier"].startswith("Umoja"))
    assert umoja["deliveries"] >= 2 and umoja["score"] is not None and umoja["avg_days_to_pay"] is not None
    own = client.get(f"{A}/performance/suppliers", headers=ag).json()
    assert len(own) == 1 and own[0]["supplier"].startswith("Umoja")
    dash = client.get(f"{A}/meal/dashboard", headers=h(client, "meal")).json()
    assert dash["reach"]["schools_served"] >= 2 and Decimal(str(dash["finance"]["paid"])) >= Decimal("39000")
    assert dash["sourcing"]["smallholder_share"]["pct"] > 0 and dash["sourcing"]["producers"] >= 2
    csv = client.get(f"{A}/meal/exports/invoices.csv", headers=h(client, "meal"))
    assert csv.status_code == 200 and inv["reference"] in csv.text and "text/csv" in csv.headers["content-type"]
    prod = client.get(f"{A}/meal/exports/producers.csv", headers=h(client, "meal")).text
    assert "Farmer 0" not in prod and "women_producers" in prod
    assert client.get(f"{A}/meal/exports/invoices.csv", headers=h(client, "school.admin")).status_code == 403


def test_complaints_lifecycle_and_public_grievance(client):
    sa, cpo, ca, ag = h(client, "school.admin"), h(client, "procurement"), h(client, "county.admin"), h(client, "aggregator")
    sup = next(c for c in client.get(f"{A}/performance/suppliers", headers=cpo).json() if c["supplier"].startswith("Umoja"))["supplier_id"]
    r = client.post(f"{A}/complaints", headers=sa, json={"category": "food_quality", "subject": "Beans with stones",
                                                         "description": "Two sacks of beans had many small stones.", "supplier_id": sup})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["school"] == "Kalulini" and c["county"] == "Makueni County"
    assert "investigate" not in c["actions"]
    assert any(x["id"] == c["id"] for x in client.get(f"{A}/complaints", headers=cpo).json())
    assert client.post(f"{A}/complaints/{c['id']}/actions", headers=sa, json={"action": "resolve", "note": "self"}).status_code == 403
    assert client.post(f"{A}/complaints/{c['id']}/actions", headers=cpo, json={"action": "investigate", "note": "Asked the hub for sorting records"}).json()["status"] == "investigating"
    assert client.post(f"{A}/complaints/{c['id']}/actions", headers=ag, json={"action": "respond", "note": "We will re-sort and replace"}).status_code == 200
    assert client.post(f"{A}/complaints/{c['id']}/actions", headers=cpo, json={"action": "resolve", "note": "x"}).status_code == 403  # cmp:approve only
    assert client.post(f"{A}/complaints/{c['id']}/actions", headers=ca, json={"action": "resolve", "note": "Supplier replaced 20 kg"}).json()["status"] == "resolved"
    done = client.post(f"{A}/complaints/{c['id']}/actions", headers=sa, json={"action": "confirm", "satisfaction": 4}).json()
    assert done["status"] == "closed" and done["satisfaction"] == 4 and len(done["history"]) == 5
    # sensitive complaints are hidden from the supplier they concern
    f = client.post(f"{A}/complaints", headers=sa, json={"category": "fraud", "subject": "Request for a kickback",
                                                         "description": "The delivery team asked for money to deliver full sacks.", "supplier_id": sup}).json()
    assert f["priority"] == "high"
    assert not any(x["id"] == f["id"] for x in client.get(f"{A}/complaints", headers=ag).json())
    # public grievance with a case number routed to the county
    r = client.post(f"{A}/public/contact", json={"name": "Parent", "contact": "0711000000", "topic": "grievance", "category": "late_delivery",
                                                 "message": "Lunch was not served on Monday because food had not arrived.",
                                                 "county_id": str(org_id("MAKUENI"))}).json()
    assert r["reference"].startswith("CMP-")
    pub = next(x for x in client.get(f"{A}/complaints", headers=ca).json() if x["reference"] == r["reference"])
    assert pub["channel"] == "public" and pub["contact"] == "0711000000"
