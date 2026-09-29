"""Contracts, framework call-offs and purchase orders (FR-CON-01…04, BR-008)."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, current_principal, ensure_in_scope, require, scope_for
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import (Commodity, Contract, ContractKind, ContractLine, ContractStatus, POLine, POStatus,
                        PurchaseOrder)
from app.services import audit, notifications as note

router = APIRouter(tags=["contracts & orders"])
Q = Decimal("0.01")


def contract_out(db: Session, c: Contract) -> dict:
    comms = {x.code: x.name for x in db.scalars(select(Commodity)).all()}
    ordered_value = sum((Decimal(ln.quantity_ordered or 0) * ln.unit_price for ln in c.lines), Decimal(0))
    today = date.today()
    alerts = []
    if c.status == ContractStatus.active and (c.ends_on - today).days <= 14:
        alerts.append("Expires within 14 days" if c.ends_on >= today else "Past end date")
    if c.kind == ContractKind.framework and c.value and ordered_value / c.value >= Decimal("0.9"):
        alerts.append("90% of contract value used")
    return {"id": c.id, "reference": c.reference, "event_id": c.event_id, "supplier": c.supplier.legal_name if c.supplier else None,
            "supplier_id": c.supplier_id, "kind": c.kind.value, "value": c.value, "ordered_value": ordered_value.quantize(Q),
            "remaining_value": (c.value - ordered_value).quantize(Q), "starts_on": c.starts_on, "ends_on": c.ends_on,
            "status": c.status.value, "alerts": alerts,
            "lines": [{"id": ln.id, "commodity_code": ln.commodity_code, "commodity": comms.get(ln.commodity_code, ln.commodity_code),
                       "unit": ln.unit, "quantity": ln.quantity, "unit_price": ln.unit_price,
                       "quantity_ordered": ln.quantity_ordered, "remaining": ln.remaining} for ln in c.lines]}


def po_out(db: Session, po: PurchaseOrder) -> dict:
    comms = {x.code: x.name for x in db.scalars(select(Commodity)).all()}
    return {"id": po.id, "reference": po.reference, "contract_id": po.contract_id,
            "contract": po.contract.reference if po.contract else None,
            "supplier": po.supplier.legal_name if po.supplier else None, "status": po.status.value, "total": po.total,
            "delivery_window": po.delivery_window, "issued_at": po.issued_at, "acknowledged_at": po.acknowledged_at,
            "lines": [{"commodity": comms.get(ln.commodity_code, ln.commodity_code), "unit": ln.unit, "quantity": ln.quantity,
                       "unit_price": ln.unit_price, "value": (ln.quantity * ln.unit_price).quantize(Q), "schools": ln.schools,
                       "dispatched_qty": ln.dispatched_qty or 0, "accepted_qty": ln.accepted_qty or 0,
                       "rejected_qty": ln.rejected_qty or 0}
                      for ln in po.lines]}


class CallOffLine(BaseModel):
    contract_line_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class CallOffIn(BaseModel):
    lines: list[CallOffLine] = Field(min_length=1)
    delivery_window: str = ""


@router.get("/contracts")
def contracts(p: Principal = Depends(require("con:view")), db: Session = Depends(get_db)):
    stmt = select(Contract).options(selectinload(Contract.lines), selectinload(Contract.supplier))
    allowed = scope_for(db, p, "con:view")
    if allowed is not None:
        stmt = stmt.where(Contract.county_id.in_(allowed))
    return [contract_out(db, c) for c in db.scalars(stmt.order_by(Contract.created_at.desc())).all()]


@router.get("/contracts/{cid}")
def contract(cid: uuid.UUID, p: Principal = Depends(require("con:view")), db: Session = Depends(get_db)):
    c = db.scalar(select(Contract).where(Contract.id == cid).options(selectinload(Contract.lines), selectinload(Contract.supplier)))
    if c is None:
        raise AppError(404, "NOT_FOUND", "Contract not found.")
    if c.county_id:
        ensure_in_scope(db, p, "con:view", c.county_id)
    pos = db.scalars(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.supplier),
                                                   selectinload(PurchaseOrder.contract))
                     .where(PurchaseOrder.contract_id == c.id).order_by(PurchaseOrder.issued_at)).all()
    return {**contract_out(db, c), "orders": [po_out(db, po) for po in pos]}


@router.post("/contracts/{cid}/call-offs", status_code=201)
def call_off(cid: uuid.UUID, body: CallOffIn, request: Request, p: Principal = Depends(require("con:create")),
             db: Session = Depends(get_db)):
    """BR-008: a call-off cannot exceed the remaining contract quantity. Funds were committed at contract level."""
    c = db.scalar(select(Contract).where(Contract.id == cid).options(selectinload(Contract.lines), selectinload(Contract.supplier)))
    if c is None:
        raise AppError(404, "NOT_FOUND", "Contract not found.")
    if c.county_id:
        ensure_in_scope(db, p, "con:create", c.county_id)
    if c.kind != ContractKind.framework:
        raise AppError(409, "NOT_FRAMEWORK", "Call-offs apply to framework agreements only.")
    if c.status != ContractStatus.active or c.ends_on < date.today():
        raise AppError(409, "CONTRACT_INACTIVE", "This contract is not active.")
    lines = {ln.id: ln for ln in c.lines}
    n = (db.scalar(select(func.count()).select_from(PurchaseOrder)) or 0) + 1
    po = PurchaseOrder(reference=f"PO-{utcnow():%Y}-{n:05d}", contract_id=c.id, supplier_id=c.supplier_id, county_id=c.county_id,
                       total=Decimal(0), issued_at=utcnow(), delivery_window=body.delivery_window, created_by=p.id)
    for li in body.lines:
        cl = lines.get(li.contract_line_id)
        if cl is None:
            raise AppError(422, "VALIDATION_ERROR", "Unknown contract line.")
        if li.quantity > cl.remaining:
            raise AppError(409, "CONTRACT_BALANCE", f"Only {cl.remaining} {cl.unit} of {cl.commodity_code} remain on this contract.")
        cl.quantity_ordered = Decimal(cl.quantity_ordered or 0) + li.quantity
        po.lines.append(POLine(contract_line_id=cl.id, commodity_code=cl.commodity_code, unit=cl.unit,
                               quantity=li.quantity, unit_price=cl.unit_price))
        po.total += (li.quantity * cl.unit_price).quantize(Q)
    db.add(po)
    db.flush()
    if all(ln.remaining <= 0 for ln in c.lines):
        c.status = ContractStatus.completed
    note.to_users(db, note.users_of_org(db, c.supplier.organization_id), f"New call-off order {po.reference}",
                  f"KSh {po.total:,.0f} under {c.reference}.", "/app/orders", "po", sms=True)
    audit.record(db, action="CALL_OFF", entity="purchase_order", entity_id=po.id, user=p.user,
                 after={"contract": c.reference, "total": po.total}, request=request)
    db.commit()
    return po_out(db, db.scalar(select(PurchaseOrder).where(PurchaseOrder.id == po.id).options(
        selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.supplier), selectinload(PurchaseOrder.contract))))


@router.get("/purchase-orders")
def purchase_orders(p: Principal = Depends(require("con:view")), db: Session = Depends(get_db)):
    stmt = select(PurchaseOrder).options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.supplier),
                                         selectinload(PurchaseOrder.contract))
    allowed = scope_for(db, p, "con:view")
    if allowed is not None:
        stmt = stmt.where(PurchaseOrder.county_id.in_(allowed))
    return [po_out(db, po) for po in db.scalars(stmt.order_by(PurchaseOrder.issued_at.desc())).all()]


# ---------------- notifications ----------------
@router.get("/notifications")
def notifications(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models import Notification
    rows = db.scalars(select(Notification).where(Notification.user_id == p.id).order_by(Notification.created_at.desc()).limit(100)).all()
    return {"unread": sum(1 for n in rows if n.read_at is None),
            "items": [{"id": n.id, "title": n.title, "body": n.body, "link": n.link, "event": n.event,
                       "created_at": n.created_at, "read": n.read_at is not None} for n in rows]}


@router.post("/notifications/read")
def mark_read(ids: list[uuid.UUID] | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from app.models import Notification
    q = select(Notification).where(Notification.user_id == p.id, Notification.read_at.is_(None))
    if ids:
        q = q.where(Notification.id.in_(ids))
    for n in db.scalars(q):
        n.read_at = utcnow()
    db.commit()
    return {"ok": True}
