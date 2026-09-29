"""Supplier-facing procurement: opportunities, clarifications, sealed bids, outcomes, orders (FR-PRO-03/04/10)."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, current_principal
from app.core.errors import AppError
from app.core.timeutil import as_utc, utcnow
from app.models import (Bid, BidStatus, Clarification, Contract, EventStatus, POStatus, ProcurementEvent,
                        PurchaseOrder, Supplier)
from app.api.v1.procurement import event_out, load_event, refresh_status
from app.services import audit, evaluation as ev_svc, notifications as note, sealing

router = APIRouter(prefix="/supplier", tags=["supplier portal"])
VISIBLE = (EventStatus.open, EventStatus.closed, EventStatus.under_evaluation, EventStatus.evaluated,
           EventStatus.approved, EventStatus.awarded, EventStatus.cancelled)


def my_supplier(db: Session, p: Principal) -> Supplier:
    orgs = {ur.org_id for ur in p.user.roles if ur.is_active and ur.org_id}
    s = db.scalar(select(Supplier).options(selectinload(Supplier.documents)).where(Supplier.organization_id.in_(orgs))) if orgs else None
    if s is None:
        raise AppError(403, "NOT_A_SUPPLIER", "Only supplier accounts can use this.")
    return s


class BidLine(BaseModel):
    lot_id: uuid.UUID
    unit_price: Decimal = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    notes: str = ""


class BidIn(BaseModel):
    lines: list[BidLine] = Field(min_length=1)
    delivery_plan: str = Field(default="", max_length=2000)
    technical_notes: str = Field(default="", max_length=4000)


class QuestionIn(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    kind: str = Field(default="question", pattern="^(question|award_query)$")


def _my_bid(db, e, s) -> Bid | None:
    return db.scalar(select(Bid).where(Bid.event_id == e.id, Bid.supplier_id == s.id))


def _bid_view(b: Bid | None, e) -> dict | None:
    if b is None:
        return None
    # the supplier may see its own bid; decrypt its own sealed copy
    contents = b.opened_payload or (sealing.unseal(b.sealed_payload) if b.sealed_payload else None)
    return {"id": b.id, "status": b.status.value, "revision": b.revision, "submitted_at": b.submitted_at,
            "contents": contents, "receipt": b.payload_sha256[:16] if b.payload_sha256 else None}


@router.get("/opportunities")
def opportunities(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = my_supplier(db, p)
    rows = db.scalars(select(ProcurementEvent).options(selectinload(ProcurementEvent.lots), selectinload(ProcurementEvent.county))
                      .where(ProcurementEvent.status.in_(VISIBLE)).order_by(ProcurementEvent.closes_at.desc())).all()
    out = []
    for e in rows:
        refresh_status(db, e)
        b = _my_bid(db, e, s)
        why = ev_svc.eligibility(e, s)
        if (e.status != EventStatus.open and b is None) or not e.lots:
            continue   # after closing suppliers only see events they bid on; events without lots can't be bid on
        out.append({"id": e.id, "reference": e.reference, "title": e.title, "county": e.county.name if e.county else None,
                    "closes_at": e.closes_at, "status": e.status.value, "lot_count": len(e.lots),
                    "eligible": not why, "why_not": why, "my_bid": b.status.value if b else None})
    return out


@router.get("/opportunities/{eid}")
def opportunity(eid: uuid.UUID, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = my_supplier(db, p)
    e = load_event(db, eid)
    if e.status not in VISIBLE:
        raise AppError(404, "NOT_FOUND", "Opportunity not found.")
    b = _my_bid(db, e, s)
    clar = db.scalars(select(Clarification).where(Clarification.event_id == e.id).order_by(Clarification.created_at)).all()
    pub = [{"id": c.id, "kind": c.kind, "question": c.question, "answer": c.answer, "answered_at": c.answered_at,
            "mine": c.supplier_id == s.id} for c in clar if c.answer or c.supplier_id == s.id]
    data = event_out(db, e, officer=False)
    data.pop("estimated_value", None)
    return {**data, "eligible": not ev_svc.eligibility(e, s), "why_not": ev_svc.eligibility(e, s),
            "clarifications": pub, "my_bid": _bid_view(b, e), "server_time": utcnow()}


@router.post("/opportunities/{eid}/questions", status_code=201)
def ask(eid: uuid.UUID, body: QuestionIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = my_supplier(db, p)
    e = load_event(db, eid)
    if body.kind == "question":
        if e.status != EventStatus.open or (e.clarification_deadline and as_utc(e.clarification_deadline) < utcnow()):
            raise AppError(409, "CLOSED", "The clarification period for this opportunity has ended.")
    elif e.status != EventStatus.awarded:
        raise AppError(409, "INVALID_TRANSITION", "Award queries can be raised once the outcome is published.")
    c = Clarification(event_id=e.id, supplier_id=s.id, kind=body.kind, question=body.question, created_by=p.id)
    db.add(c)
    if e.created_by:
        note.to_users(db, [e.created_by], f"Question on {e.reference}", body.question[:140], f"/app/sourcing/{e.id}", "clarification")
    audit.record(db, action="ASK", entity="clarification", entity_id=e.id, user=p.user, request=request)
    db.commit()
    return {"message": "Your question was sent. Answers are shared with all suppliers without naming you."}


@router.put("/opportunities/{eid}/bid")
def save_bid(eid: uuid.UUID, body: BidIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Create or revise your bid. It is sealed immediately; it counts only once submitted before the deadline."""
    s = my_supplier(db, p)
    if not p.can("src:create"):
        raise AppError(403, "FORBIDDEN", "Your account cannot bid.")
    e = load_event(db, eid)
    if e.status != EventStatus.open or as_utc(e.closes_at) <= utcnow():
        raise AppError(409, "BIDDING_CLOSED", "Bidding has closed. Late bids are not accepted.")
    why = ev_svc.eligibility(e, s)
    if why:
        raise AppError(403, "NOT_ELIGIBLE", " ".join(why))
    lots = {lt.id: lt for lt in e.lots}
    if any(ln.lot_id not in lots for ln in body.lines):
        raise AppError(422, "VALIDATION_ERROR", "A line refers to a lot that is not in this opportunity.")
    payload = {"lines": [{"lot_id": str(ln.lot_id), "unit_price": str(ln.unit_price), "quantity": str(ln.quantity),
                          "notes": ln.notes} for ln in body.lines],
               "delivery_plan": body.delivery_plan, "technical_notes": body.technical_notes, "sealed_at": utcnow().isoformat()}
    token, digest = sealing.seal(payload)
    b = _my_bid(db, e, s)
    if b is None:
        b = Bid(event_id=e.id, supplier_id=s.id, created_by=p.id, revision=0, status=BidStatus.draft)
        db.add(b)
    elif b.status == BidStatus.submitted:
        b.status = BidStatus.draft      # revising un-submits until re-submitted
    elif b.status not in (BidStatus.draft, BidStatus.withdrawn):
        raise AppError(409, "LOCKED", "This bid can no longer be changed.")
    b.sealed_payload, b.payload_sha256, b.lots_bid = token, digest, len(body.lines)
    b.revision += 1
    if b.status == BidStatus.withdrawn:
        b.status = BidStatus.draft
    audit.record(db, action="SAVE_BID", entity="bid", entity_id=e.id, user=p.user,
                 after={"revision": b.revision, "sha256": digest[:12]}, request=request)   # never the contents
    db.commit()
    return _bid_view(b, e)


@router.post("/opportunities/{eid}/bid/submit")
def submit_bid(eid: uuid.UUID, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = my_supplier(db, p)
    e = load_event(db, eid)
    if e.status != EventStatus.open or as_utc(e.closes_at) <= utcnow():
        raise AppError(409, "BIDDING_CLOSED", "Bidding has closed. Late bids are not accepted.")
    b = _my_bid(db, e, s)
    if b is None or not b.sealed_payload:
        raise AppError(409, "NO_BID", "Save your prices first.")
    if b.status == BidStatus.submitted:
        return _bid_view(b, e)
    b.status, b.submitted_at = BidStatus.submitted, utcnow()
    audit.record(db, action="SUBMIT_BID", entity="bid", entity_id=e.id, user=p.user,
                 after={"revision": b.revision, "sha256": b.payload_sha256[:12]}, request=request)
    note.to_users(db, [p.id], f"Bid received: {e.reference}",
                  f"Receipt {b.payload_sha256[:16]}. You can revise it until the deadline.", f"/app/opportunities/{e.id}", "bid")
    db.commit()
    return _bid_view(b, e)


@router.post("/opportunities/{eid}/bid/withdraw")
def withdraw_bid(eid: uuid.UUID, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = my_supplier(db, p)
    e = load_event(db, eid)
    if e.status != EventStatus.open:
        raise AppError(409, "BIDDING_CLOSED", "Bids can only be withdrawn before the deadline.")
    b = _my_bid(db, e, s)
    if b is None or b.status not in (BidStatus.draft, BidStatus.submitted):
        raise AppError(409, "NO_BID", "There is no bid to withdraw.")
    b.status = BidStatus.withdrawn
    audit.record(db, action="WITHDRAW_BID", entity="bid", entity_id=e.id, user=p.user, request=request)
    db.commit()
    return _bid_view(b, e)


@router.get("/orders")
def my_orders(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = my_supplier(db, p)
    pos = db.scalars(select(PurchaseOrder).options(selectinload(PurchaseOrder.lines), selectinload(PurchaseOrder.contract))
                     .where(PurchaseOrder.supplier_id == s.id).order_by(PurchaseOrder.issued_at.desc())).all()
    cons = db.scalars(select(Contract).options(selectinload(Contract.lines)).where(Contract.supplier_id == s.id)).all()
    from app.api.v1.contracts import contract_out, po_out
    return {"contracts": [contract_out(db, c) for c in cons], "orders": [po_out(db, po) for po in pos]}


@router.post("/orders/{po_id}/acknowledge")
def acknowledge(po_id: uuid.UUID, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = my_supplier(db, p)
    po = db.get(PurchaseOrder, po_id)
    if po is None or po.supplier_id != s.id:
        raise AppError(404, "NOT_FOUND", "Order not found.")
    if po.status != POStatus.issued:
        raise AppError(409, "INVALID_TRANSITION", "This order is already acknowledged.")
    po.status, po.acknowledged_at = POStatus.acknowledged, utcnow()
    audit.record(db, action="ACKNOWLEDGE", entity="purchase_order", entity_id=po.id, user=p.user, request=request)
    db.commit()
    from app.api.v1.contracts import po_out
    return po_out(db, po)
