"""Supplier scorecards (FR-CMP-05) and MEAL indicators (SRS §3.13). Every figure is computed from transactions in
the platform — nothing is estimated. Score weights are placeholders until the programme agrees them (SRS §14)."""
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import as_utc, utcnow
from app.models import (Batch, BatchStatus, CaseStatus, Commodity, Complaint, ComplaintStatus, Dispatch, DispatchLine,
                        DispatchStatus, ExceptionCase, Intake, Invoice, InvoiceStatus, MovementStatus,
                        Payment, POStatus, ProofOfDelivery, PurchaseOrder, SchoolDemand, StockMovement, Supplier)
from app.services.stock import county_of

WEIGHTS = {"on_time": 30, "acceptance": 30, "fill": 20, "inspection": 10, "complaints": 10}
SMALLHOLDER = {"farmer", "farmer_group", "cooperative"}
INCLUSIVE = {"women", "youth", "pwd"}


def _pct(a, b):
    return round(float(a) / float(b) * 100, 1) if b else None


def _on_time(pod: ProofOfDelivery, d: Dispatch) -> bool:
    return as_utc(pod.received_at).date() <= d.planned_date + timedelta(days=1)


def scorecard(db: Session, s: Supplier, since: datetime | None = None) -> dict:
    pos = db.scalars(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(
        PurchaseOrder.supplier_id == s.id, PurchaseOrder.status != POStatus.cancelled)).all()
    if since:
        pos = [po for po in pos if as_utc(po.issued_at) >= since]
    po_ids = [po.id for po in pos]
    ordered = sum((Decimal(ln.quantity) for po in pos for ln in po.lines), Decimal(0))
    accepted = sum((Decimal(ln.accepted_qty or 0) for po in pos for ln in po.lines), Decimal(0))
    dispatches = db.scalars(select(Dispatch).options(selectinload(Dispatch.lines)).where(
        Dispatch.po_id.in_(po_ids or [uuid.uuid4()]), Dispatch.status != DispatchStatus.cancelled)).all()
    dmap = {d.id: d for d in dispatches}
    pods = db.scalars(select(ProofOfDelivery).where(ProofOfDelivery.dispatch_id.in_(list(dmap) or [uuid.uuid4()]))).all()
    on_time = sum(1 for x in pods if _on_time(x, dmap[x.dispatch_id]))
    delivered = sum((Decimal(ln.delivered_qty or 0) for d in dispatches for ln in d.lines), Decimal(0))
    acc_lines = sum((Decimal(ln.accepted_qty or 0) for d in dispatches for ln in d.lines), Decimal(0))
    batches = db.scalars(select(Batch).where(Batch.supplier_id == s.id, Batch.status.in_(
        [BatchStatus.cleared, BatchStatus.rejected, BatchStatus.depleted]))).all()
    insp_in = sum((Decimal(b.intake_qty) for b in batches), Decimal(0))
    insp_ok = sum((Decimal(b.accepted_qty) for b in batches), Decimal(0))
    complaints = db.scalars(select(Complaint).where(Complaint.supplier_id == s.id)).all()
    invoices = db.scalars(select(Invoice).where(Invoice.supplier_id == s.id, Invoice.status == InvoiceStatus.paid)).all()
    pay_days = [(as_utc(i.paid_at) - as_utc(i.submitted_at)).days for i in invoices if i.paid_at]
    parts = {
        "on_time": _pct(on_time, len(pods)),
        "acceptance": _pct(acc_lines, delivered),
        "fill": _pct(accepted, ordered) if pods else None,
        "inspection": _pct(insp_ok, insp_in),
        "complaints": (max(0.0, 100 - 100 * len(complaints) / max(len(pods), 1)) if pods else None),
    }
    have = {k: v for k, v in parts.items() if v is not None}
    score = round(sum(v * WEIGHTS[k] for k, v in have.items()) / sum(WEIGHTS[k] for k in have), 1) if len(have) >= 2 else None
    band = None if score is None else ("Good" if score >= 85 else "Fair" if score >= 70 else "Needs improvement")
    return {"supplier_id": s.id, "supplier": s.legal_name, "supplier_type": s.supplier_type.value, "county_id": s.county_id,
            "inclusion": (s.inclusion_claim or {}).get("leadership") if s.inclusion_verified else None,
            "orders": len(pos), "ordered_qty": ordered, "accepted_qty": accepted, "deliveries": len(pods), "on_time_deliveries": on_time,
            "delivered_qty": delivered, "complaints": len(complaints),
            "open_complaints": sum(1 for c in complaints if c.status in (ComplaintStatus.submitted, ComplaintStatus.investigating)),
            "avg_days_to_pay": round(sum(pay_days) / len(pay_days), 1) if pay_days else None,
            "rates": parts, "weights": WEIGHTS, "score": score, "band": band}


def _month(d) -> str:
    return f"{d:%Y-%m}"


def meal_dashboard(db: Session, counties: set[uuid.UUID] | None, start: date | None, end: date | None) -> dict:
    """Programme indicators for the counties in scope and period. None counties = national."""
    def in_period(dt) -> bool:
        if dt is None:
            return False
        d = as_utc(dt).date() if isinstance(dt, datetime) else dt
        return (start is None or d >= start) and (end is None or d <= end)

    def in_county(cid) -> bool:
        return counties is None or cid in counties

    suppliers = {s.id: s for s in db.scalars(select(Supplier)).all()}
    comms = {c.code: c.name for c in db.scalars(select(Commodity)).all()}
    pos = [po for po in db.scalars(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.status != POStatus.cancelled)).all()
           if in_county(po.county_id) and in_period(po.issued_at)]
    po_value = sum((Decimal(po.total) for po in pos), Decimal(0))

    def share(pred):
        v = sum((Decimal(po.total) for po in pos if suppliers.get(po.supplier_id) and pred(po, suppliers[po.supplier_id])), Decimal(0))
        return {"value": v, "pct": _pct(v, po_value)}
    local = share(lambda po, s: s.county_id is not None and s.county_id == po.county_id)
    smallholder = share(lambda po, s: s.supplier_type.value in SMALLHOLDER)
    inclusive = share(lambda po, s: s.inclusion_verified and (s.inclusion_claim or {}).get("leadership") in INCLUSIVE)

    dispatches = {d.id: d for d in db.scalars(select(Dispatch).options(selectinload(Dispatch.lines)).where(Dispatch.status != DispatchStatus.cancelled)).all()
                  if in_county(d.county_id)}
    pods = [x for x in db.scalars(select(ProofOfDelivery)).all() if x.dispatch_id in dispatches and in_period(x.received_at)]
    pod_keys = {(x.dispatch_id, x.school_id) for x in pods}
    lines = [ln for d in dispatches.values() for ln in d.lines if (d.id, ln.school_id) in pod_keys]
    delivered = sum((Decimal(ln.delivered_qty or 0) for ln in lines), Decimal(0))
    accepted = sum((Decimal(ln.accepted_qty or 0) for ln in lines), Decimal(0))
    on_time = sum(1 for x in pods if _on_time(x, dispatches[x.dispatch_id]))
    by_comm: dict[str, Decimal] = defaultdict(Decimal)
    for ln in lines:
        by_comm[comms.get(ln.commodity_code, ln.commodity_code)] += Decimal(ln.accepted_qty or 0)
    schools = {x.school_id for x in pods}

    demands = [d for d in db.scalars(select(SchoolDemand)).all() if in_county(d.county_id)]
    learners_by_school: dict = {}
    for d in demands:
        learners_by_school[d.school_id] = max(learners_by_school.get(d.school_id, 0), d.enrolment or 0)
    learners = sum(v for k, v in learners_by_school.items() if k in schools) if schools else 0

    meals = 0
    for m in db.scalars(select(StockMovement).where(StockMovement.source_entity == "consumption", StockMovement.status == MovementStatus.posted)).all():
        if (m.meta or {}).get("meals_served") and in_period(m.at) and (counties is None or county_of(db, m.location_id) in counties):
            meals += int(m.meta["meals_served"])

    intakes = [i for i in db.scalars(select(Intake)).all() if in_period(i.received_at) and (counties is None or county_of(db, i.location_id) in counties)]
    producers = {(i.producer_name.strip().lower(), i.producer_phone) for i in intakes}
    women = {(i.producer_name.strip().lower(), i.producer_phone) for i in intakes if i.producer_gender == "female"}
    youth = {(i.producer_name.strip().lower(), i.producer_phone) for i in intakes if i.producer_youth}
    sourced = sum((Decimal(i.quantity) for i in intakes), Decimal(0))

    invoices = [i for i in db.scalars(select(Invoice)).all() if in_county(i.county_id)]
    payments = [pm for pm in db.scalars(select(Payment)).all() if in_period(pm.paid_on)]
    inv_ids = {i.id for i in invoices}
    paid = sum((Decimal(pm.amount) for pm in payments if pm.invoice_id in inv_ids), Decimal(0))
    days = [(as_utc(i.paid_at) - as_utc(i.submitted_at)).days for i in invoices if i.paid_at and in_period(i.paid_at)]
    pending = [i for i in invoices if i.status in (InvoiceStatus.submitted, InvoiceStatus.verified, InvoiceStatus.approved, InvoiceStatus.partially_paid)]

    cases = [c for c in db.scalars(select(ExceptionCase)).all() if counties is None or c.org_id in counties]
    complaints = [c for c in db.scalars(select(Complaint)).all() if (counties is None or c.org_id in counties) and in_period(c.created_at)]
    resolved = [c for c in complaints if c.resolved_at]
    in_sla = [c for c in resolved if c.due_at and as_utc(c.resolved_at) <= as_utc(c.due_at)]

    months: dict[str, dict] = defaultdict(lambda: {"delivered_kg": Decimal(0), "paid": Decimal(0)})
    for x in pods:
        for ln in dispatches[x.dispatch_id].lines:
            if ln.school_id == x.school_id:
                months[_month(as_utc(x.received_at))]["delivered_kg"] += Decimal(ln.accepted_qty or 0)
    for pm in payments:
        if pm.invoice_id in inv_ids:
            months[_month(pm.paid_on)]["paid"] += Decimal(pm.amount)

    return {
        "period": {"from": start, "to": end},
        "reach": {"schools_served": len(schools), "learners_in_served_schools": learners, "meals_served_recorded": meals},
        "food": {"delivered_kg": delivered, "accepted_kg": accepted, "acceptance_pct": _pct(accepted, delivered),
                 "on_time_pct": _pct(on_time, len(pods)), "deliveries": len(pods),
                 "by_commodity": [{"commodity": k, "accepted_kg": v} for k, v in sorted(by_comm.items(), key=lambda kv: -kv[1])]},
        "sourcing": {"po_value": po_value, "orders": len(pos), "local_share": local, "smallholder_share": smallholder,
                     "inclusive_share": inclusive, "producers": len(producers), "women_producers_pct": _pct(len(women), len(producers)),
                     "youth_producers_pct": _pct(len(youth), len(producers)), "sourced_kg": sourced},
        "finance": {"paid": paid, "avg_days_to_pay": round(sum(days) / len(days), 1) if days else None, "invoices_pending": len(pending),
                    "pending_value": sum((Decimal(i.total) - Decimal(i.paid_amount or 0) for i in pending), Decimal(0))},
        "accountability": {"open_exceptions": sum(1 for c in cases if c.status in (CaseStatus.open, CaseStatus.in_progress)),
                           "overdue_exceptions": sum(1 for c in cases if c.status in (CaseStatus.open, CaseStatus.in_progress)
                                                     and c.due_at and as_utc(c.due_at) < utcnow()),
                           "complaints": len(complaints), "complaints_resolved_in_sla_pct": _pct(len(in_sla), len(resolved))},
        "monthly": [{"month": k, **v} for k, v in sorted(months.items())],
    }
