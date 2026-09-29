"""Logistics & delivery (SRS §3.10): dispatch from a PO, driver milestones, the school's electronic proof of
delivery (e-POD, offline-capable), automatic exceptions, and the exception register (FR-RSK-03)."""
import base64
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import Principal, ensure_in_scope, require, require_any, scope_for
from app.core.errors import AppError
from app.core.timeutil import as_utc, utcnow
from app.models import (Batch, BatchStatus, CaseStatus, Commodity, Dispatch, DispatchLine, DispatchStatus, ExceptionCase,
                        MovementType, Organization, OrgType, POLine, POStatus, ProofOfDelivery, PurchaseOrder, Role, Supplier,
                        User, UserRole)
from app.services import audit, exceptions as exc, notifications as note, stock
from app.services.refs import next_ref

router = APIRouter(tags=["logistics & delivery"])
Q = Decimal("0.01")
OPEN_PO = (POStatus.acknowledged, POStatus.partially_fulfilled)
LIVE = (DispatchStatus.dispatched, DispatchStatus.in_transit, DispatchStatus.delivered)


def _comms(db):
    return {c.code: c.name for c in db.scalars(select(Commodity)).all()}


def _load(db, did) -> Dispatch:
    d = db.scalar(select(Dispatch).where(Dispatch.id == did).options(
        selectinload(Dispatch.lines).selectinload(DispatchLine.school), selectinload(Dispatch.source)))
    if d is None:
        raise AppError(404, "NOT_FOUND", "Dispatch not found.")
    return d


def _supplier_org(db, po: PurchaseOrder):
    s = db.get(Supplier, po.supplier_id)
    return s.organization_id if s else None


def committed_by_school(db, po_line_ids) -> dict[tuple, Decimal]:
    """Quantity already on its way or accepted per (po_line, school). Rejected goods can be re-dispatched."""
    out: dict[tuple, Decimal] = defaultdict(Decimal)
    rows = db.execute(select(DispatchLine, Dispatch.status).join(Dispatch, Dispatch.id == DispatchLine.dispatch_id)
                      .where(DispatchLine.po_line_id.in_(po_line_ids or [uuid.uuid4()]),
                             Dispatch.status != DispatchStatus.cancelled)).all()
    for ln, _st in rows:
        out[(ln.po_line_id, ln.school_id)] += Decimal(ln.accepted_qty) if ln.accepted_qty is not None else Decimal(ln.quantity)
    return out


def dispatch_out(db, d: Dispatch, p: Principal | None = None) -> dict:
    comms = _comms(db)
    po = db.get(PurchaseOrder, d.po_id)
    pods = {x.school_id: x for x in db.scalars(select(ProofOfDelivery).where(ProofOfDelivery.dispatch_id == d.id)).all()}
    batches = {b.id: b.code for b in db.scalars(select(Batch).where(Batch.id.in_({ln.batch_id for ln in d.lines if ln.batch_id} or {uuid.uuid4()})))}
    stops: dict = {}
    for ln in d.lines:
        s = stops.setdefault(ln.school_id, {"school_id": ln.school_id, "school": ln.school.name if ln.school else "", "lines": [],
                                            "pod": None})
        s["lines"].append({"id": ln.id, "po_line_id": ln.po_line_id, "commodity_code": ln.commodity_code,
                           "commodity": comms.get(ln.commodity_code, ln.commodity_code), "unit": ln.unit,
                           "batch_id": ln.batch_id, "batch_code": batches.get(ln.batch_id), "quantity": ln.quantity,
                           "delivered_qty": ln.delivered_qty, "accepted_qty": ln.accepted_qty, "rejected_qty": ln.rejected_qty,
                           "rejection_reason": ln.rejection_reason})
    for sid, pod in pods.items():
        if sid in stops:
            stops[sid]["pod"] = {"id": pod.id, "receiver_name": pod.receiver_name, "received_at": pod.received_at,
                                 "condition": pod.condition, "remarks": pod.remarks, "status": pod.status,
                                 "signature_key": pod.signature_key, "photos": pod.photos, "captured_offline": pod.captured_offline}
    out = {"id": d.id, "reference": d.reference, "po_id": d.po_id, "po": po.reference if po else None,
           "supplier": (db.get(Supplier, po.supplier_id).legal_name if po else None),
           "source_location_id": d.source_location_id, "source": d.source.name if d.source else "", "vehicle": d.vehicle,
           "driver_user_id": d.driver_user_id, "driver_name": d.driver_name, "driver_phone": d.driver_phone,
           "planned_date": d.planned_date, "status": d.status.value, "milestones": d.milestones, "stops": list(stops.values()),
           "total_qty": sum((Decimal(ln.quantity) for ln in d.lines), Decimal(0)), "created_at": d.created_at}
    if p is not None:
        allowed = scope_for(db, p, "log:approve") if p.can("log:approve") else set()
        out["can_confirm"] = [str(sid) for sid, s in stops.items()
                              if s["pod"] is None and d.status in LIVE and (allowed is None or sid in allowed)]
        out["can_drive"] = d.status in (DispatchStatus.dispatched, DispatchStatus.in_transit) and _may_drive(db, p, d)
        out["can_dispatch"] = d.status == DispatchStatus.planned and p.can("log:submit")
    return out


def _may_drive(db, p: Principal, d: Dispatch) -> bool:
    if d.driver_user_id == p.id:
        return True
    if "driver" in p.role_keys and not p.can("log:create"):
        return False      # drivers only update their own trips
    if not p.can("log:edit"):
        return False
    allowed = scope_for(db, p, "log:edit")
    return allowed is None or d.source_location_id in allowed or (d.county_id in allowed if d.county_id else False)


# ---------------- planning inputs ----------------
@router.get("/dispatch/orders")
def orders_to_fulfil(p: Principal = Depends(require("log:create")), db: Session = Depends(get_db)):
    """Open POs in scope, with what is still to be sent per school, plus cleared stock available at hubs in scope."""
    allowed = scope_for(db, p, "log:create")
    pos = db.scalars(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.supplier))
                     .where(PurchaseOrder.status.in_(OPEN_PO)).order_by(PurchaseOrder.issued_at)).all()
    pos = [po for po in pos if allowed is None or po.county_id in allowed or (po.supplier and po.supplier.organization_id in allowed)]
    comms = _comms(db)
    done = committed_by_school(db, [ln.id for po in pos for ln in po.lines])
    out = []
    for po in pos:
        lines = []
        for ln in po.lines:
            schools = [{"school_id": s["school_id"], "name": s["name"], "qty": Decimal(str(s["qty"])),
                        "remaining": max(Decimal(str(s["qty"])) - done[(ln.id, uuid.UUID(s["school_id"]))], Decimal(0))}
                       for s in (ln.schools or [])]
            lines.append({"po_line_id": ln.id, "commodity_code": ln.commodity_code, "commodity": comms.get(ln.commodity_code, ln.commodity_code),
                          "unit": ln.unit, "quantity": ln.quantity, "dispatched_qty": ln.dispatched_qty, "accepted_qty": ln.accepted_qty,
                          "schools": schools})
        out.append({"id": po.id, "reference": po.reference, "supplier": po.supplier.legal_name if po.supplier else "",
                    "supplier_org_id": po.supplier.organization_id if po.supplier else None, "status": po.status.value,
                    "delivery_window": po.delivery_window, "lines": lines})
    hubs = [r for r in stock.balances(db, allowed) if r["batch_id"] and r["on_hand"] > 0
            and r["location_type"] in ("aggregation_centre", "warehouse")]
    cleared = {b.id for b in db.scalars(select(Batch).where(Batch.id.in_({r["batch_id"] for r in hubs} or {uuid.uuid4()}),
                                                            Batch.status == BatchStatus.cleared))}
    return {"orders": out, "stock": [r for r in hubs if r["batch_id"] in cleared]}


@router.get("/dispatch/drivers")
def drivers(p: Principal = Depends(require("log:create")), db: Session = Depends(get_db)):
    allowed = scope_for(db, p, "log:create")
    rows = db.execute(select(User, UserRole.org_id).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
                      .where(Role.key == "driver", UserRole.is_active)).all()
    return [{"id": u.id, "name": u.full_name, "phone": u.phone or ""} for u, oid in rows
            if allowed is None or oid is None or oid in allowed]


# ---------------- dispatches ----------------
class DLineIn(BaseModel):
    po_line_id: uuid.UUID
    school_id: uuid.UUID
    batch_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class DispatchIn(BaseModel):
    po_id: uuid.UUID
    source_location_id: uuid.UUID
    vehicle: str = ""
    driver_user_id: uuid.UUID | None = None
    driver_name: str = ""
    driver_phone: str = ""
    planned_date: date
    lines: list[DLineIn] = Field(min_length=1)


@router.get("/dispatches")
def list_dispatches(status: str | None = None, p: Principal = Depends(require("log:view")), db: Session = Depends(get_db)):
    q = select(Dispatch).options(selectinload(Dispatch.lines).selectinload(DispatchLine.school), selectinload(Dispatch.source))
    if status:
        q = q.where(Dispatch.status.in_([DispatchStatus(s) for s in status.split(",")]))
    rows = db.scalars(q.order_by(Dispatch.planned_date.desc(), Dispatch.created_at.desc()).limit(200)).all()
    allowed = scope_for(db, p, "log:view")
    driver_only = "driver" in p.role_keys and not p.can("log:create")

    def visible(d):
        if d.driver_user_id == p.id:
            return True
        if driver_only:
            return False
        return allowed is None or d.source_location_id in allowed or (d.county_id in allowed if d.county_id else False) \
            or any(ln.school_id in allowed for ln in d.lines)
    return [dispatch_out(db, d, p) for d in rows if visible(d)]


@router.get("/dispatches/{did}")
def get_dispatch(did: uuid.UUID, p: Principal = Depends(require("log:view")), db: Session = Depends(get_db)):
    d = _load(db, did)
    if d.driver_user_id != p.id:
        if "driver" in p.role_keys and not p.can("log:create"):
            raise AppError(403, "OUT_OF_SCOPE", "This trip is not assigned to you.")
        ensure_in_scope(db, p, "log:view", d.source_location_id, d.county_id, *[ln.school_id for ln in d.lines])
    return dispatch_out(db, d, p)


@router.post("/dispatches", status_code=201)
def create_dispatch(body: DispatchIn, request: Request, p: Principal = Depends(require("log:create")), db: Session = Depends(get_db)):
    po = db.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.id == body.po_id))
    if po is None:
        raise AppError(404, "NOT_FOUND", "Purchase order not found.")
    ensure_in_scope(db, p, "log:create", po.county_id, _supplier_org(db, po))
    if po.status not in OPEN_PO:
        raise AppError(409, "PO_NOT_OPEN", "The supplier must acknowledge the order before goods are dispatched."
                       if po.status == POStatus.issued else "This order is closed.")
    src = db.get(Organization, body.source_location_id)
    if src is None or src.type not in (OrgType.aggregation_centre, OrgType.warehouse):
        raise AppError(422, "VALIDATION_ERROR", "Dispatch from a hub or warehouse.", [{"field": "source_location_id", "message": "Required"}])
    ensure_in_scope(db, p, "log:create", src.id, po.county_id)
    pol = {ln.id: ln for ln in po.lines}
    done = committed_by_school(db, list(pol))
    per_batch: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    per_stop: dict[tuple, Decimal] = defaultdict(Decimal)
    d = Dispatch(reference=next_ref(db, Dispatch, "DSP"), po_id=po.id, source_location_id=src.id, county_id=po.county_id,
                 vehicle=body.vehicle.strip().upper(), driver_user_id=body.driver_user_id, driver_name=body.driver_name.strip(),
                 driver_phone=body.driver_phone.strip(), planned_date=body.planned_date, milestones=[], created_by=p.id)
    if body.driver_user_id:
        du = db.get(User, body.driver_user_id)
        if du is None:
            raise AppError(422, "VALIDATION_ERROR", "Unknown driver.")
        d.driver_name = d.driver_name or du.full_name
        d.driver_phone = d.driver_phone or (du.phone or "")
    for i, li in enumerate(body.lines):
        ln = pol.get(li.po_line_id)
        if ln is None:
            raise AppError(422, "VALIDATION_ERROR", "That line is not on this order.", [{"field": f"lines.{i}", "message": "Unknown PO line"}])
        sch = {uuid.UUID(s["school_id"]): Decimal(str(s["qty"])) for s in (ln.schools or [])}
        if li.school_id not in sch:
            raise AppError(422, "VALIDATION_ERROR", "That school is not on this order line.", [{"field": f"lines.{i}", "message": "School not on order"}])
        b = db.get(Batch, li.batch_id)
        if b is None or b.status != BatchStatus.cleared or b.commodity_code != ln.commodity_code:
            raise AppError(409, "BATCH_NOT_CLEARED", "Choose a batch of the same commodity that has passed inspection.",
                           [{"field": f"lines.{i}", "message": "Batch not cleared / wrong commodity"}])
        per_batch[b.id] += li.quantity
        per_stop[(ln.id, li.school_id)] += li.quantity
        remaining = sch[li.school_id] - done[(ln.id, li.school_id)]
        if per_stop[(ln.id, li.school_id)] > remaining:
            raise AppError(409, "OVER_ORDER", f"Only {max(remaining, 0)} {ln.unit} of {ln.commodity_code} remain to be sent to this school.",
                           [{"field": f"lines.{i}", "message": f"Max {max(remaining, 0)}"}])
        d.lines.append(DispatchLine(po_line_id=ln.id, batch_id=b.id, school_id=li.school_id, commodity_code=ln.commodity_code,
                                    unit=ln.unit, quantity=li.quantity.quantize(Q)))
    for bid, q in per_batch.items():
        stock.ensure_available(db, src.id, bid, q, db.get(Batch, bid).code)
    d.milestones = [{"status": "planned", "at": utcnow().isoformat(), "by": p.user.full_name, "note": ""}]
    db.add(d)
    db.flush()
    audit.record(db, action="DISPATCH_PLAN", entity="dispatch", entity_id=d.id, user=p.user,
                 after={"po": po.reference, "lines": len(d.lines), "source": src.name}, request=request)
    db.commit()
    return dispatch_out(db, _load(db, d.id), p)


@router.post("/dispatches/{did}/dispatch")
def do_dispatch(did: uuid.UUID, request: Request, p: Principal = Depends(require("log:submit")), db: Session = Depends(get_db)):
    d = _load(db, did)
    ensure_in_scope(db, p, "log:submit", d.source_location_id, d.county_id)
    if d.status != DispatchStatus.planned:
        raise AppError(409, "INVALID_STATE", "Only a planned dispatch can be sent.")
    per_batch: dict = defaultdict(Decimal)
    for ln in d.lines:
        per_batch[ln.batch_id] += Decimal(ln.quantity)
    for bid, q in per_batch.items():
        stock.ensure_available(db, d.source_location_id, bid, q, db.get(Batch, bid).code)
    for ln in d.lines:
        stock.post(db, location_id=d.source_location_id, batch_id=ln.batch_id, commodity_code=ln.commodity_code, unit=ln.unit,
                   quantity=-Decimal(ln.quantity), type_=MovementType.issue, source_entity="dispatch", source_ref=d.reference,
                   reason=f"To {ln.school.name}", user_id=p.id)
        pl = db.get(POLine, ln.po_line_id)
        pl.dispatched_qty = Decimal(pl.dispatched_qty or 0) + Decimal(ln.quantity)
    for bid in per_batch:
        b = db.get(Batch, bid)
        if stock.balance(db, b.location_id, b.id) <= 0 and b.location_id == d.source_location_id:
            b.status = BatchStatus.depleted
    d.status = DispatchStatus.dispatched
    d.milestones = [*d.milestones, {"status": "dispatched", "at": utcnow().isoformat(), "by": p.user.full_name, "note": ""}]
    schools = {ln.school_id for ln in d.lines}
    for sid in schools:
        note.to_users(db, note.users_of_org(db, sid), f"Delivery {d.reference} is on its way",
                      f"Vehicle {d.vehicle or '—'}, driver {d.driver_name or '—'}. Confirm receipt when it arrives.",
                      f"/app/deliveries?dispatch={d.id}", "dispatch", sms=True)
    if d.driver_user_id:
        note.to_users(db, [d.driver_user_id], f"Trip {d.reference} assigned", f"{len(schools)} school stop(s).",
                      f"/app/deliveries?dispatch={d.id}", "dispatch", sms=True)
    audit.record(db, action="DISPATCH", entity="dispatch", entity_id=d.id, user=p.user, after={"status": "dispatched"}, request=request)
    db.commit()
    return dispatch_out(db, _load(db, d.id), p)


@router.post("/dispatches/{did}/cancel")
def cancel_dispatch(did: uuid.UUID, request: Request, p: Principal = Depends(require("log:create")), db: Session = Depends(get_db)):
    d = _load(db, did)
    ensure_in_scope(db, p, "log:create", d.source_location_id, d.county_id)
    if d.status != DispatchStatus.planned:
        raise AppError(409, "INVALID_STATE", "Only a planned dispatch can be cancelled.")
    d.status = DispatchStatus.cancelled
    d.milestones = [*d.milestones, {"status": "cancelled", "at": utcnow().isoformat(), "by": p.user.full_name, "note": ""}]
    audit.record(db, action="DISPATCH_CANCEL", entity="dispatch", entity_id=d.id, user=p.user, request=request)
    db.commit()
    return dispatch_out(db, _load(db, d.id), p)


class MilestoneIn(BaseModel):
    status: str                       # in_transit | arrived | delivered
    school_id: uuid.UUID | None = None
    note: str = ""
    lat: float | None = None
    lng: float | None = None


@router.post("/dispatches/{did}/milestones")
def milestone(did: uuid.UUID, body: MilestoneIn, request: Request, p: Principal = Depends(require_any("log:edit", "log:create")),
              db: Session = Depends(get_db)):
    d = _load(db, did)
    if not _may_drive(db, p, d):
        raise AppError(403, "OUT_OF_SCOPE", "Only the assigned driver or logistics staff can update this trip.")
    if body.status not in ("in_transit", "arrived", "delivered"):
        raise AppError(422, "VALIDATION_ERROR", "Status must be in_transit, arrived or delivered.")
    if d.status not in (DispatchStatus.dispatched, DispatchStatus.in_transit):
        raise AppError(409, "INVALID_STATE", "This trip is not on the road.")
    school = None
    if body.school_id:
        school = next((ln.school for ln in d.lines if ln.school_id == body.school_id), None)
        if school is None:
            raise AppError(422, "VALIDATION_ERROR", "That school is not a stop on this trip.")
    entry = {"status": body.status, "at": utcnow().isoformat(), "by": p.user.full_name, "note": body.note.strip()}
    if school:
        entry["school"] = school.name
    if body.lat is not None and body.lng is not None:
        entry["lat"], entry["lng"] = round(body.lat, 5), round(body.lng, 5)
    d.milestones = [*d.milestones, entry]
    if body.status == "in_transit":
        d.status = DispatchStatus.in_transit
    elif body.status == "delivered":
        d.status = DispatchStatus.delivered
    audit.record(db, action="MILESTONE", entity="dispatch", entity_id=d.id, user=p.user, after=entry, request=request)
    db.commit()
    return dispatch_out(db, _load(db, d.id), p)


# ---------------- e-POD ----------------
class PODLine(BaseModel):
    line_id: uuid.UUID
    accepted_qty: Decimal = Field(ge=0)
    rejected_qty: Decimal = Field(default=Decimal(0), ge=0)
    rejection_reason: str = ""


class PODIn(BaseModel):
    school_id: uuid.UUID
    receiver_name: str = Field(min_length=2, max_length=160)
    received_at: datetime | None = None
    condition: str = "good"           # good | damaged | wet | pests | short
    remarks: str = ""
    signature: str = ""               # data:image/png;base64,…
    photos: list[str] = []
    lines: list[PODLine] = Field(min_length=1)
    captured_offline: bool = False
    client_ref: str | None = Field(default=None, max_length=64)


def _save_signature(data_url: str) -> str:
    if not data_url:
        return ""
    if not data_url.startswith("data:image/png;base64,"):
        raise AppError(422, "VALIDATION_ERROR", "Signature must be a PNG image.", [{"field": "signature", "message": "Invalid"}])
    raw = base64.b64decode(data_url.split(",", 1)[1], validate=False)
    if not raw.startswith(b"\x89PNG") or len(raw) > 512 * 1024:
        raise AppError(422, "VALIDATION_ERROR", "Signature image is invalid or too large.", [{"field": "signature", "message": "Invalid"}])
    key = f"field/{utcnow():%Y%m}/sig-{uuid.uuid4().hex}.png"
    path = Path(settings.storage_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return key


def _update_po_status(db, po_id):
    po = db.scalar(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.id == po_id))
    if po is None or po.status == POStatus.cancelled:
        return
    if all(Decimal(ln.accepted_qty or 0) >= Decimal(ln.quantity) for ln in po.lines):
        po.status = POStatus.fulfilled
    elif any(Decimal(ln.accepted_qty or 0) > 0 for ln in po.lines):
        po.status = POStatus.partially_fulfilled


@router.post("/dispatches/{did}/pod", status_code=201)
def proof_of_delivery(did: uuid.UUID, body: PODIn, request: Request, p: Principal = Depends(require("log:approve")),
                      db: Session = Depends(get_db)):
    if body.client_ref:
        prev = db.scalar(select(ProofOfDelivery).where(ProofOfDelivery.client_ref == body.client_ref))
        if prev:
            return {**dispatch_out(db, _load(db, prev.dispatch_id), p), "duplicate": True}
    d = _load(db, did)
    ensure_in_scope(db, p, "log:approve", body.school_id)
    stop = [ln for ln in d.lines if ln.school_id == body.school_id]
    if not stop:
        raise AppError(422, "VALIDATION_ERROR", "Your school is not a stop on this delivery.")
    if d.status not in LIVE:
        raise AppError(409, "INVALID_STATE", "This delivery has not been dispatched." if d.status == DispatchStatus.planned
                       else "This delivery is already closed.")
    if db.scalar(select(ProofOfDelivery.id).where(ProofOfDelivery.dispatch_id == d.id, ProofOfDelivery.school_id == body.school_id)):
        raise AppError(409, "ALREADY_CONFIRMED", "Receipt for this delivery has already been confirmed.")
    given = {x.line_id: x for x in body.lines}
    missing = [ln for ln in stop if ln.id not in given]
    if missing:
        raise AppError(422, "VALIDATION_ERROR", "Enter the quantity received for every item.", [{"field": "lines", "message": "Incomplete"}])
    comms = _comms(db)
    school = stop[0].school
    county = d.county_id or stock.county_of(db, school.id)
    po = db.get(PurchaseOrder, d.po_id)
    short_items, rejected_items = [], []
    for ln in stop:
        g = given[ln.id]
        if g.accepted_qty + g.rejected_qty > Decimal(ln.quantity):
            raise AppError(422, "VALIDATION_ERROR", f"More than was sent ({ln.quantity} {ln.unit}) for {comms.get(ln.commodity_code)}.",
                           [{"field": f"line.{ln.id}", "message": f"Max {ln.quantity}"}])
        if g.rejected_qty > 0 and not g.rejection_reason.strip():
            raise AppError(422, "VALIDATION_ERROR", "Give a reason for rejected goods.", [{"field": f"line.{ln.id}", "message": "Reason required"}])
        ln.accepted_qty, ln.rejected_qty = g.accepted_qty.quantize(Q), g.rejected_qty.quantize(Q)
        ln.delivered_qty = (g.accepted_qty + g.rejected_qty).quantize(Q)
        ln.rejection_reason = g.rejection_reason.strip()[:300]
        if ln.accepted_qty > 0:
            stock.post(db, location_id=school.id, batch_id=ln.batch_id, commodity_code=ln.commodity_code, unit=ln.unit,
                       quantity=ln.accepted_qty, type_=MovementType.receipt, source_entity="pod", source_ref=d.reference,
                       reason="Received at school", user_id=p.id)
        if ln.rejected_qty > 0:
            stock.post(db, location_id=d.source_location_id, batch_id=ln.batch_id, commodity_code=ln.commodity_code, unit=ln.unit,
                       quantity=ln.rejected_qty, type_=MovementType.return_, source_entity="pod", source_ref=d.reference,
                       reason=f"Rejected at {school.name}: {ln.rejection_reason}", user_id=p.id)
            rejected_items.append(f"{comms.get(ln.commodity_code, ln.commodity_code)} {ln.rejected_qty} {ln.unit} ({ln.rejection_reason})")
        short = Decimal(ln.quantity) - ln.delivered_qty
        if short > 0:
            short_items.append(f"{comms.get(ln.commodity_code, ln.commodity_code)} short by {short} {ln.unit}")
        pl = db.get(POLine, ln.po_line_id)
        pl.accepted_qty = Decimal(pl.accepted_qty or 0) + ln.accepted_qty
        pl.rejected_qty = Decimal(pl.rejected_qty or 0) + ln.rejected_qty
    total_acc = sum((ln.accepted_qty for ln in stop), Decimal(0))
    status = "rejected" if total_acc == 0 else ("partially_accepted" if (short_items or rejected_items) else "accepted")
    pod = ProofOfDelivery(dispatch_id=d.id, school_id=school.id, receiver_user_id=p.id, receiver_name=body.receiver_name.strip(),
                          received_at=body.received_at or utcnow(), condition=body.condition, remarks=body.remarks.strip(),
                          signature_key=_save_signature(body.signature), photos=body.photos[:10], status=status,
                          captured_offline=body.captured_offline, client_ref=body.client_ref or None, created_by=p.id)
    db.add(pod)
    common = dict(entity="dispatch", entity_id=d.id, entity_ref=d.reference, org_id=county, supplier_id=po.supplier_id if po else None,
                  user_id=p.id)
    if rejected_items:
        exc.raise_case(db, category="rejected_goods", severity="high", title=f"Goods rejected at {school.name}",
                       detail="; ".join(rejected_items), **common)
    if short_items:
        exc.raise_case(db, category="short_delivery", severity="medium", title=f"Short delivery to {school.name}",
                       detail="; ".join(short_items), **common)
    if body.condition not in ("good", "short") and not rejected_items:
        exc.raise_case(db, category="damaged", severity="medium", title=f"Goods received in poor condition at {school.name}",
                       detail=f"Condition: {body.condition}. {body.remarks}".strip(), **common)
    received = as_utc(pod.received_at)
    if received.date() > d.planned_date + timedelta(days=1):
        exc.raise_case(db, category="late_delivery", severity="low", title=f"Late delivery to {school.name}",
                       detail=f"Planned {d.planned_date:%d %b}, received {received:%d %b %Y}.", **common)
    d.milestones = [*d.milestones, {"status": "received", "at": utcnow().isoformat(), "by": p.user.full_name,
                                    "school": school.name, "note": status.replace("_", " ")}]
    db.flush()
    schools = {ln.school_id for ln in d.lines}
    confirmed = set(db.scalars(select(ProofOfDelivery.school_id).where(ProofOfDelivery.dispatch_id == d.id)))
    if schools <= confirmed:
        d.status = DispatchStatus.closed
        d.milestones = [*d.milestones, {"status": "closed", "at": utcnow().isoformat(), "by": "system", "note": "All stops confirmed"}]
    _update_po_status(db, d.po_id)
    if po:
        sup = db.get(Supplier, po.supplier_id)
        note.to_users(db, note.users_of_org(db, sup.organization_id) if sup else [], f"{school.name} confirmed delivery {d.reference}",
                      f"Status: {status.replace('_', ' ')}.", "/app/orders", "pod", sms=True)
    audit.record(db, action="POD", entity="dispatch", entity_id=d.id, user=p.user,
                 after={"school": school.name, "status": status, "accepted": total_acc, "offline": body.captured_offline},
                 request=request)
    db.commit()
    return {**dispatch_out(db, _load(db, d.id), p), "duplicate": False}


# ---------------- exceptions register ----------------
def case_out(db, c: ExceptionCase) -> dict:
    org = db.get(Organization, c.org_id) if c.org_id else None
    sup = db.get(Supplier, c.supplier_id) if c.supplier_id else None
    ru = db.get(User, c.resolved_by) if c.resolved_by else None
    due = as_utc(c.due_at)
    return {"id": c.id, "reference": c.reference, "category": c.category, "severity": c.severity, "entity": c.entity,
            "entity_id": c.entity_id, "entity_ref": c.entity_ref, "org": org.name if org else None,
            "supplier": sup.legal_name if sup else None, "title": c.title, "detail": c.detail, "owner_role": c.owner_role,
            "due_at": c.due_at, "overdue": bool(due and due < utcnow() and c.status in (CaseStatus.open, CaseStatus.in_progress)),
            "status": c.status.value, "corrective_action": c.corrective_action, "resolution": c.resolution,
            "resolved_by": ru.full_name if ru else None, "resolved_at": c.resolved_at, "created_at": c.created_at}


@router.get("/exceptions")
def list_cases(status: str | None = None, p: Principal = Depends(require("rsk:view")), db: Session = Depends(get_db)):
    q = select(ExceptionCase)
    allowed = scope_for(db, p, "rsk:view")
    if allowed is not None:
        q = q.where(ExceptionCase.org_id.in_(allowed))
    if status:
        q = q.where(ExceptionCase.status.in_([CaseStatus(s) for s in status.split(",")]))
    return [case_out(db, c) for c in db.scalars(q.order_by(ExceptionCase.created_at.desc()).limit(300)).all()]


class CaseActionIn(BaseModel):
    text: str = Field(min_length=3)


def _case(db, p, cid, *codes) -> ExceptionCase:
    c = db.get(ExceptionCase, cid)
    if c is None:
        raise AppError(404, "NOT_FOUND", "Exception not found.")
    code = next((x for x in codes if p.can(x)), None)
    if code is None:
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    ensure_in_scope(db, p, code, c.org_id)
    return c


@router.post("/exceptions/{cid}/progress")
def case_progress(cid: uuid.UUID, body: CaseActionIn, request: Request, p: Principal = Depends(require_any("rsk:create", "rsk:edit")),
                  db: Session = Depends(get_db)):
    c = _case(db, p, cid, "rsk:edit", "rsk:create")
    if c.status not in (CaseStatus.open, CaseStatus.in_progress):
        raise AppError(409, "INVALID_STATE", "This exception is already resolved.")
    c.status, c.corrective_action = CaseStatus.in_progress, body.text.strip()
    audit.record(db, action="EXCEPTION_PROGRESS", entity="exception_case", entity_id=c.id, user=p.user, after={"action": c.corrective_action},
                 request=request)
    db.commit()
    return case_out(db, c)


@router.post("/exceptions/{cid}/resolve")
def case_resolve(cid: uuid.UUID, body: CaseActionIn, request: Request, p: Principal = Depends(require_any("rsk:approve", "rsk:edit")),
                 db: Session = Depends(get_db)):
    c = _case(db, p, cid, "rsk:edit", "rsk:approve")
    if c.status not in (CaseStatus.open, CaseStatus.in_progress):
        raise AppError(409, "INVALID_STATE", "This exception is already resolved.")
    c.status, c.resolution, c.resolved_by, c.resolved_at = CaseStatus.resolved, body.text.strip(), p.id, utcnow()
    audit.record(db, action="EXCEPTION_RESOLVE", entity="exception_case", entity_id=c.id, user=p.user, after={"resolution": c.resolution},
                 request=request)
    db.commit()
    return case_out(db, c)
