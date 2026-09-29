"""Inventory (SRS §3.9): balances from the movement ledger, transfers, approved adjustments/write-offs,
physical counts with reconciliation, and school consumption."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, ensure_in_scope, require, scope_for
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import (Batch, BatchStatus, Commodity, InstanceStatus, MovementStatus, MovementType, Organization, OrgType,
                        StockCount, StockMovement, User, WorkflowInstance)
from app.services import audit, exceptions as exc, stock, workflow as wf
from app.services.refs import next_ref

router = APIRouter(prefix="/inventory", tags=["inventory"])
Q = Decimal("0.01")
STOCK_TYPES = (OrgType.aggregation_centre, OrgType.warehouse, OrgType.school)


def _loc(db, lid, code: str, p: Principal) -> Organization:
    o = db.get(Organization, lid)
    if o is None or o.type not in STOCK_TYPES:
        raise AppError(422, "VALIDATION_ERROR", "Choose a hub, warehouse or school.")
    ensure_in_scope(db, p, code, o.id)
    return o


def movement_out(db, m: StockMovement, locs=None, batches=None, wfs=None) -> dict:
    loc = (locs or {}).get(m.location_id) or db.get(Organization, m.location_id)
    b = (batches or {}).get(m.batch_id) if batches is not None else (db.get(Batch, m.batch_id) if m.batch_id else None)
    u = db.get(User, m.created_by) if m.created_by else None
    out = {"id": m.id, "at": m.at, "location_id": m.location_id, "location": loc.name if loc else "", "batch_id": m.batch_id,
           "batch_code": b.code if b else None, "commodity_code": m.commodity_code, "unit": m.unit, "quantity": m.quantity,
           "type": m.type.value, "status": m.status.value, "source_entity": m.source_entity, "source_ref": m.source_ref,
           "reason": m.reason, "by": u.full_name if u else ""}
    if wfs is not None and m.id in wfs:
        out["workflow_id"] = wfs[m.id]
    return out


@router.get("/balances")
def get_balances(location_id: uuid.UUID | None = None, p: Principal = Depends(require("inv:view")),
                 db: Session = Depends(get_db)):
    allowed = scope_for(db, p, "inv:view")
    ids = allowed
    if location_id:
        if allowed is not None and location_id not in allowed:
            raise AppError(403, "OUT_OF_SCOPE", "This location is outside your assigned area.")
        ids = {location_id}
    rows = stock.balances(db, ids)
    comms = {c.code: c.name for c in db.scalars(select(Commodity)).all()}
    for r in rows:
        r["commodity"] = comms.get(r["commodity_code"], r["commodity_code"])
    return rows


@router.get("/movements")
def movements(location_id: uuid.UUID | None = None, batch_id: uuid.UUID | None = None, status: str | None = None,
              p: Principal = Depends(require("inv:view")), db: Session = Depends(get_db)):
    q = select(StockMovement)
    allowed = scope_for(db, p, "inv:view")
    if allowed is not None:
        q = q.where(StockMovement.location_id.in_(allowed))
    if location_id:
        q = q.where(StockMovement.location_id == location_id)
    if batch_id:
        q = q.where(StockMovement.batch_id == batch_id)
    if status:
        q = q.where(StockMovement.status == MovementStatus(status))
    rows = db.scalars(q.order_by(StockMovement.at.desc()).limit(300)).all()
    locs = {o.id: o for o in db.scalars(select(Organization).where(Organization.id.in_({m.location_id for m in rows} or {uuid.uuid4()}))).all()}
    batches = {b.id: b for b in db.scalars(select(Batch).where(Batch.id.in_({m.batch_id for m in rows if m.batch_id} or {uuid.uuid4()}))).all()}
    pend = [m.id for m in rows if m.status == MovementStatus.pending_approval]
    wfs = {i.entity_id: i.id for i in db.scalars(select(WorkflowInstance).where(
        WorkflowInstance.entity == "stock_movement", WorkflowInstance.entity_id.in_(pend or [uuid.uuid4()]),
        WorkflowInstance.status == InstanceStatus.active)).all()}
    return [movement_out(db, m, locs, batches, wfs) for m in rows]


# ---------------- transfers ----------------
class TransferIn(BaseModel):
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    batch_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    note: str = ""


@router.post("/transfers", status_code=201)
def transfer(body: TransferIn, request: Request, p: Principal = Depends(require("inv:create")), db: Session = Depends(get_db)):
    src = _loc(db, body.from_location_id, "inv:create", p)
    dst = db.get(Organization, body.to_location_id)
    if dst is None or dst.type not in STOCK_TYPES or dst.id == src.id:
        raise AppError(422, "VALIDATION_ERROR", "Choose a different destination hub, warehouse or school.")
    b = db.get(Batch, body.batch_id)
    if b is None or b.status not in (BatchStatus.cleared,):
        raise AppError(409, "BATCH_NOT_CLEARED", "Only batches cleared by quality inspection can be moved.")
    stock.ensure_available(db, src.id, b.id, body.quantity, b.code)
    ref = f"TRF-{utcnow():%Y%m%d%H%M%S}"
    out_m = stock.post(db, location_id=src.id, batch_id=b.id, commodity_code=b.commodity_code, unit=b.unit, quantity=-body.quantity,
                       type_=MovementType.transfer_out, source_entity="transfer", source_ref=ref, reason=f"To {dst.name}. {body.note}".strip(),
                       user_id=p.id)
    stock.post(db, location_id=dst.id, batch_id=b.id, commodity_code=b.commodity_code, unit=b.unit, quantity=body.quantity,
               type_=MovementType.transfer_in, source_entity="transfer", source_ref=ref, reason=f"From {src.name}. {body.note}".strip(),
               user_id=p.id)
    audit.record(db, action="TRANSFER", entity="batch", entity_id=b.id, user=p.user,
                 after={"from": src.name, "to": dst.name, "qty": body.quantity}, request=request)
    db.commit()
    return movement_out(db, out_m)


# ---------------- adjustments / write-offs (approval required, FR-INV-04) ----------------
class AdjustmentIn(BaseModel):
    location_id: uuid.UUID
    batch_id: uuid.UUID | None = None
    commodity_code: str | None = None
    quantity: Decimal                  # signed: negative reduces stock
    type: str = "adjustment"           # adjustment | waste
    reason: str = Field(min_length=5)


def _adj_complete(db, inst, p, note):
    m = db.get(StockMovement, inst.entity_id)
    if m.quantity < 0:
        have = stock.balance(db, m.location_id, m.batch_id, m.commodity_code)
        if have + m.quantity < 0:
            raise AppError(409, "INSUFFICIENT_STOCK", f"Stock is now {have}; this adjustment would make it negative.")
    m.status = MovementStatus.posted


def _adj_reject(db, inst, p, note):
    db.get(StockMovement, inst.entity_id).status = MovementStatus.rejected


wf.DEFINITIONS["stock_adjustment"].hooks.update(complete=_adj_complete, reject=_adj_reject, **{"return": _adj_reject})


@router.post("/adjustments", status_code=201)
def adjustment(body: AdjustmentIn, request: Request, p: Principal = Depends(require("inv:create")), db: Session = Depends(get_db)):
    loc = _loc(db, body.location_id, "inv:create", p)
    if body.quantity == 0:
        raise AppError(422, "VALIDATION_ERROR", "Quantity cannot be zero.", [{"field": "quantity", "message": "Cannot be zero"}])
    try:
        t = {"adjustment": MovementType.adjustment, "waste": MovementType.waste}[body.type]
    except KeyError:
        raise AppError(422, "VALIDATION_ERROR", "Type must be adjustment or waste.")
    if t == MovementType.waste and body.quantity > 0:
        raise AppError(422, "VALIDATION_ERROR", "A write-off reduces stock: enter a negative quantity.",
                       [{"field": "quantity", "message": "Must be negative"}])
    b = db.get(Batch, body.batch_id) if body.batch_id else None
    comm = b.commodity_code if b else body.commodity_code
    if not comm:
        raise AppError(422, "VALIDATION_ERROR", "Choose a batch or commodity.")
    if body.quantity < 0 and b is not None:
        stock.ensure_available(db, loc.id, b.id, -body.quantity, b.code)
    m = stock.post(db, location_id=loc.id, batch_id=b.id if b else None, commodity_code=comm, unit=b.unit if b else "kg",
                   quantity=body.quantity, type_=t, status=MovementStatus.pending_approval, source_entity="adjustment",
                   reason=body.reason.strip(), user_id=p.id)
    inst = wf.start(db, "stock_adjustment", entity="stock_movement", entity_id=m.id,
                    entity_ref=f"{'Write-off' if t == MovementType.waste else 'Adjustment'} {m.quantity} {m.unit} · {loc.name}",
                    title=f"{'Write-off' if t == MovementType.waste else 'Stock adjustment'} at {loc.name}", scope_org_id=loc.id,
                    initiator=p, context={"reason": m.reason})
    audit.record(db, action="ADJUSTMENT_REQUEST", entity="stock_movement", entity_id=m.id, user=p.user,
                 after={"qty": m.quantity, "type": t.value, "location": loc.name}, reason=m.reason, request=request)
    db.commit()
    return {**movement_out(db, m), "workflow": wf.serialize(inst, p, db)}


# ---------------- stock counts (FR-INV-06) ----------------
class CountLine(BaseModel):
    batch_id: uuid.UUID | None = None
    commodity_code: str
    counted_qty: Decimal = Field(ge=0)


class CountIn(BaseModel):
    location_id: uuid.UUID
    lines: list[CountLine] = Field(min_length=1)
    note: str = ""


def count_out(db, c: StockCount, p=None) -> dict:
    loc = db.get(Organization, c.location_id)
    inst = db.scalar(select(WorkflowInstance).options(selectinload(WorkflowInstance.actions)).where(
        WorkflowInstance.entity == "stock_count", WorkflowInstance.entity_id == c.id).order_by(WorkflowInstance.started_at.desc()))
    return {"id": c.id, "reference": c.reference, "location_id": c.location_id, "location": loc.name if loc else "",
            "lines": c.lines, "status": c.status, "note": c.note, "created_at": c.created_at,
            "workflow": wf.serialize(inst, p, db) if inst else None}


def _count_complete(db, inst, p, note):
    c = db.get(StockCount, inst.entity_id)
    c.status = "approved"
    big = []
    for ln in c.lines:
        var = Decimal(ln["variance"])
        if var == 0:
            continue
        stock.post(db, location_id=c.location_id, batch_id=uuid.UUID(ln["batch_id"]) if ln.get("batch_id") else None,
                   commodity_code=ln["commodity_code"], quantity=var, type_=MovementType.adjustment, source_entity="stock_count",
                   source_ref=c.reference, reason=f"Count variance ({c.reference})", user_id=p.id)
        sys_q = Decimal(ln["system_qty"])
        if sys_q and abs(var) / sys_q > Decimal("0.02"):
            big.append(f"{ln.get('batch_code') or ln['commodity_code']}: {var}")
    if big:
        exc.raise_case(db, category="stock_variance", severity="medium", entity="stock_count", entity_id=c.id,
                       entity_ref=c.reference, org_id=stock.county_of(db, c.location_id),
                       title="Stock count variance above 2%", detail="; ".join(big), user_id=p.id)


def _count_reject(db, inst, p, note):
    db.get(StockCount, inst.entity_id).status = "rejected"


wf.DEFINITIONS["stock_count"].hooks.update(complete=_count_complete, reject=_count_reject, **{"return": _count_reject})


@router.get("/counts")
def counts(p: Principal = Depends(require("inv:view")), db: Session = Depends(get_db)):
    q = select(StockCount)
    allowed = scope_for(db, p, "inv:view")
    if allowed is not None:
        q = q.where(StockCount.location_id.in_(allowed))
    return [count_out(db, c, p) for c in db.scalars(q.order_by(StockCount.created_at.desc()).limit(100)).all()]


@router.post("/counts", status_code=201)
def create_count(body: CountIn, request: Request, p: Principal = Depends(require("inv:create")), db: Session = Depends(get_db)):
    loc = _loc(db, body.location_id, "inv:create", p)
    lines = []
    for ln in body.lines:
        b = db.get(Batch, ln.batch_id) if ln.batch_id else None
        sys_q = stock.balance(db, loc.id, b.id if b else None, ln.commodity_code)
        lines.append({"batch_id": str(b.id) if b else None, "batch_code": b.code if b else None, "commodity_code": ln.commodity_code,
                      "system_qty": str(sys_q), "counted_qty": str(ln.counted_qty.quantize(Q)),
                      "variance": str((ln.counted_qty - sys_q).quantize(Q))})
    c = StockCount(reference=next_ref(db, StockCount, "CNT", 4), location_id=loc.id, lines=lines, status="submitted",
                   note=body.note.strip(), created_by=p.id)
    db.add(c)
    db.flush()
    variance = sum(abs(Decimal(x["variance"])) for x in lines)
    if variance == 0:
        c.status = "approved"
    else:
        wf.start(db, "stock_count", entity="stock_count", entity_id=c.id, entity_ref=c.reference,
                 title=f"Stock count at {loc.name}", scope_org_id=loc.id, initiator=p)
    audit.record(db, action="STOCK_COUNT", entity="stock_count", entity_id=c.id, user=p.user,
                 after={"location": loc.name, "lines": len(lines), "total_abs_variance": variance}, request=request)
    db.commit()
    return count_out(db, c, p)


# ---------------- school consumption ----------------
class ConsumptionIn(BaseModel):
    location_id: uuid.UUID
    commodity_code: str
    quantity: Decimal = Field(gt=0)
    served_on: date | None = None
    meals_served: int | None = Field(default=None, ge=0)
    note: str = ""


@router.post("/consumption", status_code=201)
def consumption(body: ConsumptionIn, request: Request, p: Principal = Depends(require("inv:create")), db: Session = Depends(get_db)):
    """Record food used for meals at a school. Draws down stock first-expiring/first-received first."""
    loc = _loc(db, body.location_id, "inv:create", p)
    if loc.type != OrgType.school:
        raise AppError(422, "VALIDATION_ERROR", "Consumption is recorded at schools.")
    have = stock.balance(db, loc.id, None, body.commodity_code)
    if body.quantity > have:
        raise AppError(409, "INSUFFICIENT_STOCK", f"Only {have} in stock at this school.", [{"available": str(have)}])
    rows = [r for r in stock.balances(db, {loc.id}) if r["commodity_code"] == body.commodity_code and r["on_hand"] > 0
            and not any(a.startswith("RECALLED") for a in r["alerts"])]
    usable = sum((r["on_hand"] for r in rows), Decimal(0))
    if body.quantity > usable:
        raise AppError(409, "INSUFFICIENT_STOCK", f"Only {usable} usable in stock (recalled batches cannot be used).", [{"available": str(usable)}])
    rows.sort(key=lambda r: (r["expiry_date"] or date.max, r["batch_code"] or ""))
    left, posted = body.quantity, []
    label = f"Meals {body.served_on or date.today():%d %b %Y}" + (f" · {body.meals_served} served" if body.meals_served else "")
    for r in rows:
        if left <= 0:
            break
        take = min(left, r["on_hand"])
        posted.append(stock.post(db, location_id=loc.id, batch_id=r["batch_id"], commodity_code=body.commodity_code, unit=r["unit"],
                                 quantity=-take, type_=MovementType.issue, source_entity="consumption", source_ref=label,
                                 reason=body.note.strip(), user_id=p.id,
                                 meta=None if posted else {"meals_served": body.meals_served, "served_on": str(body.served_on or date.today())}))
        left -= take
    audit.record(db, action="CONSUMPTION", entity="organization", entity_id=loc.id, user=p.user,
                 after={"commodity": body.commodity_code, "qty": body.quantity, "meals": body.meals_served}, request=request)
    db.commit()
    return [movement_out(db, m) for m in posted]
