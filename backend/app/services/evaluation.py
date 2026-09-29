"""Bid eligibility and evaluation scoring (FR-PRO-06…09, BR-002, BR-014).

Per lot, among *responsive* bids (eligible supplier, full quantity offered, price > 0):
  technical  = Σ evaluator-scored criteria (mean across evaluators) + auto criteria
  financial  = financial_weight × lowest price ÷ bid price
  total      = technical + financial (out of 100)
Auto criterion 'inclusion' = full marks when the supplier's women/youth/PWD-led status is *verified*."""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from statistics import mean

from app.models import DocumentStatus, EvaluationAssignment, ProcurementEvent, Supplier, SupplierStatus

Q = Decimal("0.01")
INCLUSIVE = {"women", "youth", "pwd"}


def eligibility(ev: ProcurementEvent, s: Supplier) -> list[str]:
    """Reasons a supplier may NOT bid (empty list ⇒ eligible)."""
    why = []
    if s.status not in (SupplierStatus.prequalified, SupplierStatus.active):
        why.append("Your supplier profile is not prequalified yet.")
    if ev.categories and not set(ev.categories) & set(s.approved_categories or []):
        why.append("You are not prequalified for these commodity categories: " + ", ".join(ev.categories) + ".")
    latest = {}
    for d in s.documents:
        if d.doc_type not in latest or d.version > latest[d.doc_type].version:
            latest[d.doc_type] = d
    for t in ev.required_docs or []:
        d = latest.get(t)
        if d is None or d.status != DocumentStatus.verified:
            why.append(f"Required document not verified: {t.replace('_', ' ')}.")
        elif d.expires_on and d.expires_on < date.today():
            why.append(f"Required document expired: {t.replace('_', ' ')}.")
    return why


def auto_scores(ev: ProcurementEvent, s: Supplier) -> dict:
    out = {}
    for c in ev.criteria:
        if c.get("auto") and c["key"] == "inclusion":
            lead = (s.inclusion_claim or {}).get("leadership")
            out["inclusion"] = float(c["max"]) if (s.inclusion_verified and lead in INCLUSIVE) else 0.0
    return out


def consolidate(ev: ProcurementEvent, bids: list, assignments: list[EvaluationAssignment]) -> dict:
    scorers = [a for a in assignments if a.submitted_at and not a.has_conflict]
    manual = [c for c in ev.criteria if not c.get("auto")]
    fin_w = Decimal(ev.financial_weight)
    lots_out = []
    for lot in ev.lots:
        rows = []
        for b in bids:
            line = next((ln for ln in (b.opened_payload or {}).get("lines", []) if ln["lot_id"] == str(lot.id)), None)
            if line is None:
                continue
            price, qty = Decimal(str(line["unit_price"])), Decimal(str(line["quantity"]))
            issues = list(eligibility(ev, b.supplier))
            if qty < Decimal(lot.quantity):
                issues.append(f"Offers {qty} of {lot.quantity} {lot.unit} required.")
            if price <= 0:
                issues.append("No valid price.")
            tech_parts = {}
            for c in manual:
                vals = [float(a.scores.get(str(b.id), {}).get(c["key"], 0) or 0) for a in scorers]
                tech_parts[c["key"]] = round(min(float(c["max"]), mean(vals)) if vals else 0.0, 2)
            tech_parts.update(auto_scores(ev, b.supplier))
            rows.append({"bid_id": str(b.id), "supplier_id": str(b.supplier_id), "supplier": b.supplier.legal_name,
                         "unit_price": str(price), "quantity": str(qty), "value": str((price * Decimal(lot.quantity)).quantize(Q)),
                         "responsive": not issues, "issues": issues, "technical": tech_parts,
                         "technical_total": round(sum(tech_parts.values()), 2)})
        responsive = [r for r in rows if r["responsive"]]
        low = min((Decimal(r["unit_price"]) for r in responsive), default=None)
        for r in rows:
            fin = (fin_w * low / Decimal(r["unit_price"])).quantize(Q, ROUND_HALF_UP) if (r["responsive"] and low) else Decimal(0)
            r["financial"] = float(fin)
            r["total"] = round(r["technical_total"] + float(fin), 2) if r["responsive"] else 0.0
        rows.sort(key=lambda r: (not r["responsive"], -r["total"], Decimal(r["unit_price"])))
        for i, r in enumerate(rows, 1):
            r["rank"] = i if r["responsive"] else None
        rec = next((r for r in rows if r["responsive"]), None)
        lots_out.append({"lot_id": str(lot.id), "lot_no": lot.lot_no, "name": lot.name, "commodity_code": lot.commodity_code,
                         "quantity": str(lot.quantity), "unit": lot.unit, "bids": rows,
                         "recommended": rec["bid_id"] if rec else None})
    total = sum((Decimal(next(r["value"] for r in lo["bids"] if r["bid_id"] == lo["recommended"]))
                 for lo in lots_out if lo["recommended"]), Decimal(0))
    return {"lots": lots_out, "evaluators": [a.user.full_name for a in scorers], "recommended_total": str(total.quantize(Q)),
            "unawarded_lots": [lo["lot_no"] for lo in lots_out if not lo["recommended"]]}
