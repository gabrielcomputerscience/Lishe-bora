"""Phase 6 analytics: stock-out forecasting, requirement projection, price intelligence and automated risk flags.

Methods are deliberately simple and explainable (averages, medians, rule thresholds) so county staff can check them.
Thresholds live in the system setting "risk.rules" and can be changed without a code deployment (FR-PLT-05)."""
import statistics
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import as_utc, utcnow
from app.models import (Batch, BatchStatus, Bid, BidStatus, CaseStatus, Commodity, Complaint, ComplaintStatus, Contract, Dispatch,
                        DispatchStatus, DemandStatus, EventStatus, ExceptionCase, Invoice, InvoiceStatus, MovementStatus,
                        Organization, OrgType, ProcurementEvent, ProofOfDelivery, SchoolDemand, StockMovement, Supplier,
                        SupplierStatus, SystemSetting)
from app.services import stock
from app.services.exceptions import raise_case

DEFAULT_RULES = {
    "late_deliveries": {"window_days": 90, "medium": 2, "high": 4},
    "quality_rejection_pct": {"medium": 20, "high": 40},
    "school_acceptance_pct_below": {"medium": 90, "high": 75},
    "price_above_median_pct": {"medium": 25, "high": 50},
    "single_bid_award": {"severity": "medium"},
    "invoice_returns": {"medium": 2, "high": 4},
    "expired_documents": {"severity": "medium"},
    "stock_expiry_days": {"low": 14},
    "stockout_days": {"high": 5, "medium": 10},
}
WEIGHT = {"high": 3, "medium": 2, "low": 1}


def rules(db: Session) -> dict:
    s = db.scalar(select(SystemSetting).where(SystemSetting.key == "risk.rules"))
    out = {k: dict(v) for k, v in DEFAULT_RULES.items()}
    for k, v in ((s.value if s else {}) or {}).items():
        if k in out and isinstance(v, dict):
            out[k].update(v)
    return out


def _sev(value, cfg, higher_is_worse=True):
    if higher_is_worse:
        if "high" in cfg and value >= cfg["high"]:
            return "high"
        if "medium" in cfg and value >= cfg["medium"]:
            return "medium"
    else:
        if "high" in cfg and value < cfg["high"]:
            return "high"
        if "medium" in cfg and value < cfg["medium"]:
            return "medium"
    return None


# ---------------- forecasting ----------------
def stock_outlook(db: Session, locations: set[uuid.UUID] | None) -> list[dict]:
    """Days of stock left per school and commodity, from the last 30 days' use (or the approved demand plan if no use is recorded)."""
    cfg = rules(db)["stockout_days"]
    comms = {c.code: c.name for c in db.scalars(select(Commodity)).all()}
    schools = {o.id: o for o in db.scalars(select(Organization).where(Organization.type == OrgType.school)).all()
               if locations is None or o.id in locations}
    on_hand: dict = defaultdict(Decimal)
    for r in stock.balances(db, set(schools)):
        if not any(a.startswith("RECALLED") for a in r["alerts"]):
            on_hand[(r["location_id"], r["commodity_code"])] += Decimal(r["on_hand"])
    since = utcnow() - timedelta(days=30)
    used: dict = defaultdict(Decimal)
    for m in db.scalars(select(StockMovement).where(StockMovement.source_entity == "consumption", StockMovement.status == MovementStatus.posted,
                                                    StockMovement.location_id.in_(set(schools) or {uuid.uuid4()}))).all():
        if as_utc(m.at) >= since:
            used[(m.location_id, m.commodity_code)] += -Decimal(m.quantity)
    planned: dict = {}
    for d in db.scalars(select(SchoolDemand).options(selectinload(SchoolDemand.lines)).where(
            SchoolDemand.school_id.in_(set(schools) or {uuid.uuid4()}),
            SchoolDemand.status.in_([DemandStatus.approved, DemandStatus.converted]))).all():
        for ln in d.lines:
            if d.feeding_days:
                planned[(d.school_id, ln.commodity_code)] = Decimal(ln.final_qty) / Decimal(d.feeding_days)
    out = []
    for key in set(on_hand) | set(used):
        sid, comm = key
        daily = used[key] / 30 if used.get(key) else None
        basis = "recorded use (30 days)"
        if not daily and key in planned:
            daily, basis = planned[key], "demand plan"
        have = on_hand.get(key, Decimal(0))
        days = float(have / daily) if daily else None
        sev = None
        if days is not None:
            sev = "high" if days < cfg["high"] else "medium" if days < cfg["medium"] else None
        out.append({"school_id": sid, "school": schools[sid].name, "commodity_code": comm, "commodity": comms.get(comm, comm),
                    "on_hand": have, "daily_use": round(float(daily), 2) if daily else None, "days_left": round(days, 1) if days is not None else None,
                    "stockout_on": (date.today() + timedelta(days=int(days))) if days is not None else None, "basis": basis, "risk": sev})
    return sorted(out, key=lambda r: (r["days_left"] is None, r["days_left"] or 0))


def requirement_projection(db: Session, counties: set[uuid.UUID] | None) -> list[dict]:
    """Per commodity: last approved plan, what schools accepted and used, stock now, and a suggested next-term quantity."""
    comms = {c.code: c for c in db.scalars(select(Commodity)).all()}
    demands = [d for d in db.scalars(select(SchoolDemand).options(selectinload(SchoolDemand.lines)).where(
        SchoolDemand.status.in_([DemandStatus.approved, DemandStatus.converted]))).all() if counties is None or d.county_id in counties]
    latest: dict = {}
    for d in demands:
        if d.school_id not in latest or as_utc(d.created_at) > as_utc(latest[d.school_id].created_at):
            latest[d.school_id] = d
    planned: dict = defaultdict(Decimal)
    for d in latest.values():
        for ln in d.lines:
            planned[ln.commodity_code] += Decimal(ln.final_qty)
    school_ids = set(latest) | {o.id for o in db.scalars(select(Organization).where(Organization.type == OrgType.school)).all()
                                if counties is None or stock.county_of(db, o.id) in counties}
    accepted: dict = defaultdict(Decimal)
    used: dict = defaultdict(Decimal)
    for m in db.scalars(select(StockMovement).where(StockMovement.location_id.in_(school_ids or {uuid.uuid4()}),
                                                    StockMovement.status == MovementStatus.posted)).all():
        if m.source_entity == "pod":
            accepted[m.commodity_code] += Decimal(m.quantity)
        elif m.source_entity == "consumption":
            used[m.commodity_code] += -Decimal(m.quantity)
    on_hand: dict = defaultdict(Decimal)
    for r in stock.balances(db, school_ids):
        on_hand[r["commodity_code"]] += Decimal(r["on_hand"])
    out = []
    for code in sorted(set(planned) | set(accepted) | set(used)):
        suggestion = max(planned.get(code, Decimal(0)) - on_hand.get(code, Decimal(0)), Decimal(0))
        c = comms.get(code)
        out.append({"commodity_code": code, "commodity": c.name if c else code, "unit": c.unit if c else "kg",
                    "planned_last_term": planned.get(code, Decimal(0)), "accepted": accepted.get(code, Decimal(0)),
                    "used": used.get(code, Decimal(0)), "on_hand_at_schools": on_hand.get(code, Decimal(0)),
                    "suggested_next_term": suggestion,
                    "estimated_value": (suggestion * Decimal(c.reference_price)).quantize(Decimal("1")) if c and c.reference_price else None})
    return out


# ---------------- price intelligence ----------------
def price_intelligence(db: Session, counties: set[uuid.UUID] | None) -> list[dict]:
    comms = {c.code: c for c in db.scalars(select(Commodity)).all()}
    sups = {s.id: s.legal_name for s in db.scalars(select(Supplier)).all()}
    cty = {o.id: o.name for o in db.scalars(select(Organization).where(Organization.type == OrgType.county)).all()}
    pts: dict = defaultdict(list)
    for c in db.scalars(select(Contract).options(selectinload(Contract.lines))).all():
        if counties is not None and c.county_id not in counties:
            continue
        for ln in c.lines:
            pts[ln.commodity_code].append({"date": c.starts_on, "contract": c.reference, "county": cty.get(c.county_id), "supplier": sups.get(c.supplier_id),
                                           "unit_price": float(ln.unit_price), "quantity": float(ln.quantity)})
    out = []
    for code, rows in pts.items():
        rows.sort(key=lambda r: r["date"])
        prices = [r["unit_price"] for r in rows]
        med = statistics.median(prices)
        ref = float(comms[code].reference_price) if code in comms and comms[code].reference_price else None
        for r in rows:
            r["vs_median_pct"] = round((r["unit_price"] - med) / med * 100, 1) if med else None
        wavg = sum(r["unit_price"] * r["quantity"] for r in rows) / sum(r["quantity"] for r in rows) if rows else None
        out.append({"commodity_code": code, "commodity": comms[code].name if code in comms else code, "contracts": len(rows),
                    "min": min(prices), "median": med, "max": max(prices), "weighted_avg": round(wavg, 2) if wavg else None,
                    "latest": prices[-1], "reference_price": ref,
                    "latest_vs_reference_pct": round((prices[-1] - ref) / ref * 100, 1) if ref else None,
                    "trend_pct": round((prices[-1] - prices[0]) / prices[0] * 100, 1) if len(prices) > 1 and prices[0] else None,
                    "points": rows})
    return sorted(out, key=lambda r: r["commodity"])


# ---------------- risk flags ----------------
def risk_flags(db: Session, counties: set[uuid.UUID] | None) -> list[dict]:
    R = rules(db)
    flags: list[dict] = []
    sups = [s for s in db.scalars(select(Supplier).options(selectinload(Supplier.documents))).all() if counties is None or s.county_id in counties]
    today = date.today()

    def add(rule, severity, entity, entity_id, ref, title, detail, org_id=None, supplier_id=None):
        flags.append({"rule": rule, "severity": severity, "entity": entity, "entity_id": entity_id, "entity_ref": ref, "title": title,
                      "detail": detail, "org_id": org_id, "supplier_id": supplier_id})

    from app.models import PurchaseOrder
    since = utcnow() - timedelta(days=R["late_deliveries"]["window_days"])
    for s in sups:
        po_ids = list(db.scalars(select(PurchaseOrder.id).where(PurchaseOrder.supplier_id == s.id)))
        disp = {d.id: d for d in db.scalars(select(Dispatch).options(selectinload(Dispatch.lines)).where(
            Dispatch.po_id.in_(po_ids or [uuid.uuid4()]), Dispatch.status != DispatchStatus.cancelled)).all()}
        pods = db.scalars(select(ProofOfDelivery).where(ProofOfDelivery.dispatch_id.in_(list(disp) or [uuid.uuid4()]))).all()
        late = [x for x in pods if as_utc(x.received_at) >= since and as_utc(x.received_at).date() > disp[x.dispatch_id].planned_date + timedelta(days=1)]
        sev = _sev(len(late), R["late_deliveries"])
        if sev:
            add("late_deliveries", sev, "supplier", s.id, s.legal_name, f"{len(late)} late deliveries in {R['late_deliveries']['window_days']} days",
                "Deliveries received more than a day after the planned date.", s.county_id, s.id)
        delivered = sum((Decimal(ln.delivered_qty or 0) for d in disp.values() for ln in d.lines), Decimal(0))
        acc = sum((Decimal(ln.accepted_qty or 0) for d in disp.values() for ln in d.lines), Decimal(0))
        if delivered:
            pct = float(acc / delivered * 100)
            sev = _sev(pct, R["school_acceptance_pct_below"], higher_is_worse=False)
            if sev:
                add("school_acceptance", sev, "supplier", s.id, s.legal_name, f"Only {pct:.0f}% of delivered food accepted by schools",
                    f"{acc} of {delivered} kg accepted.", s.county_id, s.id)
        batches = db.scalars(select(Batch).where(Batch.supplier_id == s.id, Batch.status.in_(
            [BatchStatus.cleared, BatchStatus.rejected, BatchStatus.depleted, BatchStatus.recalled]))).all()
        intake = sum((Decimal(b.intake_qty) for b in batches), Decimal(0))
        if intake:
            rej = float(sum((Decimal(b.rejected_qty) for b in batches), Decimal(0)) / intake * 100)
            sev = _sev(rej, R["quality_rejection_pct"])
            if sev:
                add("quality_rejection", sev, "supplier", s.id, s.legal_name, f"{rej:.0f}% of intake rejected at inspection",
                    f"Across {len(batches)} inspected batch(es).", s.county_id, s.id)
        if any(b.status == BatchStatus.recalled for b in batches):
            add("recall", "high", "supplier", s.id, s.legal_name, "Supplier has a recalled batch", "See the batch recall exception.", s.county_id, s.id)
        sens = db.scalars(select(Complaint).where(Complaint.supplier_id == s.id, Complaint.category.in_(["fraud", "safeguarding"]),
                                                  Complaint.status.in_([ComplaintStatus.submitted, ComplaintStatus.investigating]))).all()
        if sens:
            add("sensitive_complaint", "high", "supplier", s.id, s.legal_name, f"{len(sens)} open fraud/safeguarding complaint(s)",
                "Handle under the whistle-blower procedure; do not share with the supplier.", s.county_id, s.id)
        returned = db.scalars(select(Invoice).where(Invoice.supplier_id == s.id, Invoice.status.in_([InvoiceStatus.returned, InvoiceStatus.rejected]))).all()
        sev = _sev(len(returned), R["invoice_returns"])
        if sev:
            add("invoice_returns", sev, "supplier", s.id, s.legal_name, f"{len(returned)} invoices returned or rejected", "", s.county_id, s.id)
        if s.status in (SupplierStatus.prequalified, SupplierStatus.active):
            expired = [d for d in s.documents if d.expires_on and d.expires_on < today]
            if expired:
                add("expired_documents", R["expired_documents"]["severity"], "supplier", s.id, s.legal_name, "Prequalified supplier with expired documents",
                    ", ".join(d.doc_type for d in expired), s.county_id, s.id)
    # contract prices far above the median for the commodity
    for pi in price_intelligence(db, counties):
        for r in pi["points"]:
            sev = _sev(r["vs_median_pct"] or 0, R["price_above_median_pct"])
            if sev and pi["contracts"] >= 3:
                c = db.scalar(select(Contract).where(Contract.reference == r["contract"]))
                add("price_outlier", sev, "contract", c.id, c.reference, f"{pi['commodity']} at {r['unit_price']:,.0f}: {r['vs_median_pct']}% above median",
                    f"Median {pi['median']:,.0f} across {pi['contracts']} contracts.", c.county_id, c.supplier_id)
    # awards with a single submitted bid
    for e in db.scalars(select(ProcurementEvent).where(ProcurementEvent.status == EventStatus.awarded)).all():
        if counties is not None and e.county_id not in counties:
            continue
        n = len(db.scalars(select(Bid.id).where(Bid.event_id == e.id, Bid.status.in_(
            [BidStatus.submitted, BidStatus.opened, BidStatus.awarded, BidStatus.unsuccessful]))).all())
        if n == 1:
            add("single_bid_award", R["single_bid_award"]["severity"], "procurement_event", e.id, e.reference, "Award made on a single bid",
                "Check that the notice reached enough suppliers.", e.county_id)
    # stock close to expiry
    for r in stock.balances(db, None):
        if r["batch_id"] and r["expiry_date"] and Decimal(r["on_hand"]) > 0 and (r["expiry_date"] - today).days <= R["stock_expiry_days"]["low"]:
            cid = stock.county_of(db, r["location_id"])
            if counties is None or cid in counties:
                add("stock_expiry", "low", "batch", r["batch_id"], r["batch_code"], f"{r['commodity']} at {r['location']} expires {r['expiry_date']:%d %b}",
                    f"{r['on_hand']} {r['unit']} on hand.", cid)
    return flags


def supplier_risk(flags: list[dict]) -> list[dict]:
    agg: dict = {}
    for f in flags:
        if f["supplier_id"]:
            a = agg.setdefault(f["supplier_id"], {"supplier_id": f["supplier_id"], "supplier": None, "score": 0, "flags": 0, "high": 0})
            a["score"] += WEIGHT[f["severity"]]
            a["flags"] += 1
            a["high"] += f["severity"] == "high"
            if f["entity"] == "supplier":
                a["supplier"] = f["entity_ref"]
    return sorted(agg.values(), key=lambda a: -a["score"])


def raise_new_cases(db: Session, flags: list[dict], user_id=None, min_severity: str = "medium") -> int:
    """Open an exception case for each new medium/high flag (once per rule and record)."""
    n = 0
    for f in flags:
        if WEIGHT[f["severity"]] < WEIGHT[min_severity]:
            continue
        key = f"{f['rule']}:{f['entity_ref']}"[:60]
        exists = db.scalar(select(ExceptionCase.id).where(ExceptionCase.category == "risk_flag", ExceptionCase.entity_ref == key,
                                                          ExceptionCase.status.in_([CaseStatus.open, CaseStatus.in_progress])))
        if exists:
            continue
        raise_case(db, category="risk_flag", severity=f["severity"], entity=f["entity"], entity_id=f["entity_id"], entity_ref=key,
                   org_id=f["org_id"], supplier_id=f["supplier_id"], title=f["title"][:200], detail=f["detail"], user_id=user_id)
        n += 1
    return n
