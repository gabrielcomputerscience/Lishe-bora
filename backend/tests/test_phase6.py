"""Phase 6: QR & recall, public verification, GIS & routes, forecasting, price intelligence, risk flags,
verified payment details, payment files, statement reconciliation, callbacks, IFMIS export, Excel export."""
import hashlib
import hmac
import json
from datetime import date

from app.core.config import settings
from tests.conftest import org_id
from tests.test_phase4 import A, h, hub, make_cleared_batch


def deliver_some_maize(client):
    bid, code = make_cleared_batch(client, commodity="MAIZE-FLOUR", qtys=(300, 200), moisture=12.5)
    lg = h(client, "logistics")
    po = next(o for o in client.get(f"{A}/dispatch/orders", headers=lg).json()["orders"] if o["reference"] == "PO-DEMO-0001")
    mz = next(ln for ln in po["lines"] if ln["commodity_code"] == "MAIZE-FLOUR")
    lines = [{"po_line_id": mz["po_line_id"], "school_id": s["school_id"], "batch_id": bid, "quantity": str(min(float(s["remaining"]), 20))}
             for s in mz["schools"] if float(s["remaining"]) > 0]
    assert lines, "the demo PO has no maize left to send"
    d = client.post(f"{A}/dispatches", headers=lg, json={"po_id": po["id"], "source_location_id": hub(), "vehicle": "KDB 9C",
                                                         "planned_date": str(date.today()), "lines": lines}).json()
    return bid, code, d, po["id"], mz["po_line_id"]


def test_route_qr_public_and_gis(client):
    bid, code, d, _, _ = deliver_some_maize(client)
    lg, meal = h(client, "logistics"), h(client, "meal")
    # the real schools have no seeded coordinates: each school captures its own (test values)
    for who, sc, lat, lng in (("school.admin", "MAKUENI-SCH001", -2.3551, 37.9012), ("school2.admin", "MAKUENI-SCH002", -2.3104, 37.8521)):
        assert client.put(f"{A}/fulfilment/locations/{org_id(sc)}/gps", headers=h(client, who), json={"lat": lat, "lng": lng}).status_code == 200
    r = client.get(f"{A}/dispatches/{d['id']}/route", headers=lg).json()
    assert r["suggested"]["order"] and r["suggested"]["total_km"] > 0 and r["suggested"]["source"]["name"].startswith("Umoja")
    assert client.post(f"{A}/dispatches/{d['id']}/route", headers=lg).json()["saved"]["order"] == r["suggested"]["order"]
    qr = client.get(f"{A}/batches/{bid}/qr.svg", headers=h(client, "aggregator"))
    assert qr.status_code == 200 and b"<svg" in qr.content
    pub = client.get(f"{A}/public/trace/{code}").json()
    assert pub["commodity"] == "Maize flour" and pub["producers"] == 2 and "Farmer 0" not in json.dumps(pub)
    assert client.get(f"{A}/public/trace/BATCH-1999-000000").status_code == 404
    m = client.get(f"{A}/gis/map", headers=meal).json()
    names = {x["name"] for x in m["points"]}
    assert "Umoja Aggregation Hub (demo)" in names and m["counts"]["mapped"] >= 2
    sa = h(client, "school.admin")
    assert client.put(f"{A}/fulfilment/locations/{org_id('MAKUENI-SCH001')}/gps", headers=sa, json={"lat": 0.6013, "lng": 34.5232}).status_code == 200
    assert client.put(f"{A}/fulfilment/locations/{org_id('MAKUENI-SCH002')}/gps", headers=sa, json={"lat": 0.6, "lng": 34.5}).status_code == 403


def test_payments_integrations_recall_and_risk(client, monkeypatch):
    bid, code, d, po_id, line = deliver_some_maize(client)
    lg = h(client, "logistics")
    d = client.post(f"{A}/dispatches/{d['id']}/dispatch", headers=lg).json()
    total_qty, got = 0, []
    for who, sc in (("school.admin", "MAKUENI-SCH001"), ("school2.admin", "MAKUENI-SCH002")):
        stop = next((s for s in d["stops"] if s["school_id"] == str(org_id(sc))), None)
        if stop:
            r = client.post(f"{A}/dispatches/{d['id']}/pod", headers=h(client, who), json={
                "school_id": stop["school_id"], "receiver_name": "Head teacher",
                "lines": [{"line_id": ln["id"], "accepted_qty": str(ln["quantity"])} for ln in stop["lines"]]})
            assert r.status_code == 201, r.text
            total_qty += sum(float(ln["quantity"]) for ln in stop["lines"])
            got.append((who, sc))
    # verified payment details: supplier requests, finance verifies
    ag, acc, fin, pay = h(client, "aggregator"), h(client, "accounts"), h(client, "finance"), h(client, "payments")
    r = client.put(f"{A}/suppliers/me/payment-details", headers=ag, json={"method": "mpesa", "account_name": "Umoja Farmers Cooperative",
                                                                          "mpesa_phone": "0712 345 678"})
    assert r.status_code == 200 and r.json()["pending"]["mpesa_phone"].endswith("5678") and "•" in r.json()["pending"]["mpesa_phone"]
    pend = client.get(f"{A}/finance/payment-details/pending", headers=acc).json()
    sup_id = next(x["supplier_id"] for x in pend if x["supplier"].startswith("Umoja"))
    assert client.post(f"{A}/finance/payment-details/{sup_id}/verify", headers=acc, json={"approve": True, "note": "Called registered number"}).status_code == 200
    # invoice → verify → approve
    inv = client.post(f"{A}/invoices", headers=ag, json={"po_id": po_id, "supplier_invoice_no": "UMJ-P6-1", "invoice_date": str(date.today()),
                                                         "lines": [{"po_line_id": line, "quantity": str(total_qty)}]}).json()
    w = inv["workflow"]["id"]
    client.post(f"{A}/workflow/{w}/act", headers=acc, json={"action": "approve"})
    client.post(f"{A}/workflow/{w}/act", headers=fin, json={"action": "approve"})
    ageing = client.get(f"{A}/finance/ageing", headers=pay).json()
    assert any(x["reference"] == inv["reference"] for x in ageing["invoices"])
    # payment file: blocked for the verifier (SoD), allowed for the payer
    blocked = client.post(f"{A}/finance/payment-files", headers=acc, json={"invoice_ids": [inv["id"]], "system": "mpesa"}).json()
    assert blocked["error"]["code"] == "PAYMENT_FILE_BLOCKED" and "segregation" in blocked["error"]["details"][0]["issue"]
    pf = client.post(f"{A}/finance/payment-files", headers=pay, json={"invoice_ids": [inv["id"]], "system": "mpesa"})
    assert pf.status_code == 201, pf.text
    f = client.get(pf.json()["download"].replace("/api/v1", A), headers=pay)
    assert "0712345678" in f.text and inv["reference"] in f.text
    # statement import reconciles the payment; a second import is recognised as duplicate
    csv = f"date,amount,transaction_ref,reference\n{date.today()},{inv['total']},RKT55AA1,LisheBora {inv['reference']}\n{date.today()},999,RKT55AA2,unknown\n"
    r = client.post(f"{A}/finance/statements", headers=pay, data={"system": "mpesa"}, files={"file": ("stmt.csv", csv, "text/csv")}).json()
    assert len(r["matched"]) == 1 and len(r["unmatched"]) == 1 and r["status"] == "partial"
    assert client.get(f"{A}/invoices/{inv['id']}", headers=pay).json()["status"] == "paid"
    r = client.post(f"{A}/finance/statements", headers=pay, data={"system": "mpesa"}, files={"file": ("stmt.csv", csv, "text/csv")}).json()
    assert len(r["duplicates"]) == 1 and not r["matched"]
    log = client.get(f"{A}/integrations/log", headers=pay).json()
    assert {x["kind"] for x in log} >= {"payment_file", "statement_import"}
    assert client.get(f"{A}/integrations/log", headers=ag).status_code == 403
    ifmis = client.get(f"{A}/finance/ifmis-export.csv", headers=pay)
    assert ifmis.status_code == 200 and inv["reference"] in ifmis.text and "DEMO-A-T3" in ifmis.text
    # signed M-Pesa callback
    assert client.post(f"{A}/integrations/mpesa/callback", content=b"{}").status_code == 503
    monkeypatch.setattr(settings, "mpesa_callback_secret", "s3cret")
    body = json.dumps({"TransID": "QX1", "TransAmount": "10", "BillRefNumber": "INV-2000-00001"}).encode()
    assert client.post(f"{A}/integrations/mpesa/callback", content=body, headers={"X-Signature": "bad"}).status_code == 401
    sig = hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert client.post(f"{A}/integrations/mpesa/callback", content=body, headers={"X-Signature": sig}).json()["ResultCode"] == 1
    # Excel export
    x = client.get(f"{A}/meal/exports/invoices.xlsx", headers=h(client, "meal"))
    assert x.status_code == 200 and x.content[:2] == b"PK"
    # recall the batch that reached schools
    qi = h(client, "inspector")
    assert client.post(f"{A}/batches/{bid}/recall", headers=ag, json={"reason": "Aflatoxin test failed at county lab"}).status_code == 403
    r = client.post(f"{A}/batches/{bid}/recall", headers=qi, json={"reason": "Aflatoxin test failed at county lab"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "recalled" and r.json()["schools_notified"] >= 1
    assert any("RECALL" in n["title"] for n in client.get(f"{A}/notifications", headers=h(client, got[0][0])).json()["items"])
    assert client.get(f"{A}/public/trace/{code}").json()["recalled"] is True
    use = client.post(f"{A}/inventory/consumption", headers=h(client, "meals.officer"),
                      json={"location_id": str(org_id("MAKUENI-SCH001")), "commodity_code": "MAIZE-FLOUR", "quantity": "100000"})
    assert use.status_code == 409
    bal = client.get(f"{A}/inventory/balances", headers=h(client, "meal")).json()
    assert any(r["batch_code"] == code and "RECALLED: do not use" in r["alerts"] for r in bal)
    # risk flags, scan (idempotent), rule tuning
    risk = h(client, "risk")
    dash = client.get(f"{A}/risk/dashboard", headers=risk).json()
    assert any(f["rule"] == "recall" for f in dash["flags"]) and dash["suppliers"]
    n1 = client.post(f"{A}/risk/scan", headers=risk).json()["new_cases"]
    assert n1 >= 1 and client.post(f"{A}/risk/scan", headers=risk).json()["new_cases"] == 0
    assert client.put(f"{A}/risk/rules", headers=risk, json={"late_deliveries": {"medium": 1}}).json()["late_deliveries"]["medium"] == 1
    assert client.put(f"{A}/risk/rules", headers=risk, json={"nope": {}}).status_code == 422
    assert client.get(f"{A}/risk/dashboard", headers=ag).status_code == 403


def test_forecast_prices_and_county_performance(client):
    cpo = h(client, "procurement")
    out = client.get(f"{A}/analytics/stock-outlook", headers=h(client, "meals.officer"))
    assert out.status_code == 200 and isinstance(out.json(), list)
    req = client.get(f"{A}/analytics/requirements", headers=cpo).json()
    assert isinstance(req, list)
    prices = client.get(f"{A}/analytics/prices", headers=cpo).json()
    assert any(p["commodity_code"] == "MAIZE-FLOUR" and p["median"] > 0 for p in prices)
    assert client.get(f"{A}/analytics/prices", headers=h(client, "supplier2")).status_code == 403
    perf = client.get(f"{A}/performance/counties", headers=h(client, "meal")).json()
    assert any(r["county"] == "Makueni County" for r in perf)
