"""Sourcing events: create from plan → approve → publish → clarifications/amendments → auto-close →
formal opening → evaluation (COI + scores) → consolidation → award approval → contracts & POs."""
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, current_principal, ensure_in_scope, require, scope_for
from app.core.errors import AppError
from app.core.timeutil import as_utc, utcnow
from app.models import (Award, AwardStatus, Bid, BidStatus, BudgetLine, Clarification, Commodity, Contract,
                        ContractKind, ContractLine, EvaluationAssignment, EventStatus, POLine, PlanStatus, POStatus,
                        ProcurementEvent, ProcurementLot, ProcurementMethod, ProcurementPlan, PurchaseOrder, Role,
                        Supplier, SupplierStatus, User, UserRole)
from app.services import audit, budget, evaluation as ev_svc, notifications as note, sealing, workflow as wf

router = APIRouter(prefix="/procurement-events", tags=["procurement"])
Q = Decimal("0.01")
LINK = "/app/sourcing/{id}"


# ---------------------------------------------------------------- helpers
def refresh_status(db: Session, e: ProcurementEvent) -> None:
    """Automatic closing at the deadline (FR-PRO-06). Lazy: runs whenever the event is read or written."""
    if e.status in (EventStatus.open, EventStatus.published) and as_utc(e.closes_at) <= utcnow():
        e.status = EventStatus.closed
        audit.record(db, action="AUTO_CLOSE", entity="procurement_event", entity_id=e.id,
                     after={"bids": db.scalar(select(func.count()).select_from(Bid).where(
                         Bid.event_id == e.id, Bid.status == BidStatus.submitted))})
        db.commit()


def load_event(db: Session, eid) -> ProcurementEvent:
    e = db.scalar(select(ProcurementEvent).where(ProcurementEvent.id == eid)
                  .options(selectinload(ProcurementEvent.lots), selectinload(ProcurementEvent.county)))
    if e is None:
        raise AppError(404, "NOT_FOUND", "Sourcing event not found.")
    refresh_status(db, e)
    return e


def lot_out(lot: ProcurementLot, comms: dict) -> dict:
    return {"id": lot.id, "lot_no": lot.lot_no, "name": lot.name, "commodity_code": lot.commodity_code,
            "commodity": comms[lot.commodity_code].name if lot.commodity_code in comms else lot.commodity_code,
            "category": lot.category, "unit": lot.unit, "quantity": lot.quantity, "specification": lot.specification,
            "delivery_window": lot.delivery_window, "schools": lot.schools}


def event_out(db: Session, e: ProcurementEvent, p: Principal | None = None, officer=True) -> dict:
    comms = {c.code: c for c in db.scalars(select(Commodity)).all()}
    submitted = db.scalar(select(func.count()).select_from(Bid).where(Bid.event_id == e.id, Bid.status.in_(
        [BidStatus.submitted, BidStatus.opened, BidStatus.awarded, BidStatus.unsuccessful]))) or 0
    out = {"id": e.id, "reference": e.reference, "title": e.title, "method": e.method.value, "county_id": e.county_id,
           "county": e.county.name if e.county else None, "plan_id": e.plan_id, "description": e.description,
           "eligibility": e.eligibility, "categories": e.categories, "closes_at": e.closes_at,
           "clarification_deadline": e.clarification_deadline, "status": e.status.value, "is_public": e.is_public,
           "technical_weight": e.technical_weight, "financial_weight": e.financial_weight, "criteria": e.criteria,
           "required_docs": e.required_docs, "contract_start": e.contract_start, "contract_end": e.contract_end,
           "estimated_value": e.estimated_value, "opened_at": e.opened_at, "bids_received": submitted,
           "lots": [lot_out(lt, comms) for lt in e.lots], "awarded_to": e.awarded_to, "awarded_value": e.awarded_value}
    if officer:
        out["results"] = e.results or None
        inst = wf.active_for(db, "procurement_event", e.id)
        out["workflow"] = wf.serialize(inst, p, db) if inst else None
        from app.models import WorkflowInstance
        hist = db.scalars(select(WorkflowInstance).where(WorkflowInstance.entity == "procurement_event",
                                                         WorkflowInstance.entity_id == e.id)
                          .order_by(WorkflowInstance.started_at)).all()
        out["history"] = [h for inst_ in hist for h in wf.serialize(inst_)["history"]]
    return out


def _officer_scope(db, p: Principal, e: ProcurementEvent, code="src:view"):
    if e.county_id:
        ensure_in_scope(db, p, code, e.county_id)
    elif not p.can(code):
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")


# ---------------------------------------------------------------- create / edit
class FromPlanIn(BaseModel):
    plan_id: uuid.UUID
    closes_at: datetime
    method: ProcurementMethod | None = None
    title: str | None = None
    contract_start: date | None = None
    contract_end: date | None = None


class EventIn(BaseModel):
    reference: str = Field(min_length=3, max_length=40)
    title: str
    method: ProcurementMethod
    county_id: uuid.UUID | None = None
    description: str = ""
    eligibility: str = ""
    categories: list[str] = Field(default_factory=list)
    estimated_value: Decimal | None = None
    closes_at: datetime
    is_public: bool = True


class Criterion(BaseModel):
    key: str = Field(pattern=r"^[a-z_]{2,20}$")
    label: str
    max: float = Field(gt=0, le=100)
    auto: bool = False


class EventUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    eligibility: str | None = None
    closes_at: datetime | None = None
    clarification_deadline: datetime | None = None
    technical_weight: int | None = Field(default=None, ge=0, le=100)
    criteria: list[Criterion] | None = None
    required_docs: list[str] | None = None
    contract_start: date | None = None
    contract_end: date | None = None
    is_public: bool | None = None
    specifications: dict[str, str] | None = None     # lot_id -> specification
    delivery_windows: dict[str, str] | None = None


def _validate_weights(e: ProcurementEvent):
    manual_auto = sum(float(c["max"]) for c in e.criteria)
    if abs(manual_auto - e.technical_weight) > 0.01:
        raise AppError(422, "WEIGHTS", f"Technical criteria add up to {manual_auto:g} but the technical weight is {e.technical_weight}.")
    if e.technical_weight + e.financial_weight != 100:
        raise AppError(422, "WEIGHTS", "Technical and financial weights must add up to 100.")


@router.get("")
def list_events(p: Principal = Depends(require("src:view")), db: Session = Depends(get_db)):
    stmt = select(ProcurementEvent).options(selectinload(ProcurementEvent.lots), selectinload(ProcurementEvent.county))
    allowed = scope_for(db, p, "src:view")
    if allowed is not None:
        stmt = stmt.where(or_(ProcurementEvent.county_id.in_(allowed), ProcurementEvent.county_id.is_(None)))
    rows = db.scalars(stmt.order_by(ProcurementEvent.closes_at.desc())).all()
    out = []
    for e in rows:
        refresh_status(db, e)
        o = event_out(db, e, officer=False)
        o.pop("lots")
        o["lot_count"] = len(e.lots)
        out.append(o)
    return out


@router.post("/from-plan", status_code=201)
def from_plan(body: FromPlanIn, request: Request, p: Principal = Depends(require("src:create")), db: Session = Depends(get_db)):
    """FR-PRO-01/02: each approved plan line becomes a lot of one sourcing event."""
    pl = db.scalar(select(ProcurementPlan).where(ProcurementPlan.id == body.plan_id).options(
        selectinload(ProcurementPlan.lines), selectinload(ProcurementPlan.term)))
    if pl is None:
        raise AppError(404, "NOT_FOUND", "Plan not found.")
    ensure_in_scope(db, p, "src:create", pl.county_id)
    if pl.status != PlanStatus.approved:
        raise AppError(409, "PLAN_NOT_APPROVED", "Only approved procurement plans can be turned into sourcing events.")
    if as_utc(body.closes_at) <= utcnow() + timedelta(hours=1):
        raise AppError(422, "VALIDATION_ERROR", "The closing time must be at least an hour from now.")
    comms = {c.code: c for c in db.scalars(select(Commodity)).all()}
    method = body.method or ProcurementMethod(pl.method if pl.method in ProcurementMethod._value2member_map_ else "rfq")
    seq = (db.scalar(select(func.count()).select_from(ProcurementEvent)) or 0) + 1
    prefix = {"framework": "FWK", "competitive": "TND"}.get(method.value, "RFQ")
    cats = sorted({comms[ln.commodity_code].category for ln in pl.lines if ln.commodity_code in comms})
    e = ProcurementEvent(reference=f"{prefix}-{pl.term.year}-{seq:04d}", title=body.title or pl.title, method=method,
                         county_id=pl.county_id, plan_id=pl.id, categories=cats,
                         eligibility="Prequalified: " + ", ".join(c.replace("_", " ") for c in cats),
                         estimated_value=pl.estimated_value, closes_at=body.closes_at,
                         clarification_deadline=as_utc(body.closes_at) - timedelta(days=2),
                         contract_start=body.contract_start or pl.term.starts_on,
                         contract_end=body.contract_end or pl.term.ends_on, created_by=p.id)
    db.add(e)
    db.flush()
    for i, ln in enumerate(pl.lines, 1):
        c = comms.get(ln.commodity_code)
        spec = ", ".join(f"{k.replace('_', ' ')} ≤ {v}" for k, v in (c.quality_spec or {}).items()) if c else ""
        e.lots.append(ProcurementLot(lot_no=i, name=f"{ln.lot} — {c.name if c else ln.commodity_code}",
                                     commodity_code=ln.commodity_code, category=c.category if c else "", unit=ln.unit,
                                     quantity=ln.quantity, specification=spec, delivery_window=ln.delivery_window,
                                     schools=ln.schools, plan_line_id=ln.id, estimated_unit_price=ln.unit_price))
    pl.status = PlanStatus.sourcing
    audit.record(db, action="CREATE", entity="procurement_event", entity_id=e.id, user=p.user,
                 after={"reference": e.reference, "plan": pl.reference, "lots": len(pl.lines)}, request=request)
    db.commit()
    return event_out(db, load_event(db, e.id), p)


@router.post("", status_code=201)
def create_event(body: EventIn, request: Request, p: Principal = Depends(require("src:create")), db: Session = Depends(get_db)):
    """Manual event (e.g. framework without a plan). Lots are added from a plan in normal use."""
    if body.county_id:
        ensure_in_scope(db, p, "src:create", body.county_id)
    if db.scalar(select(ProcurementEvent).where(ProcurementEvent.reference == body.reference)):
        raise AppError(409, "CODE_IN_USE", "This reference is already used.")
    e = ProcurementEvent(**body.model_dump(), created_by=p.id)
    db.add(e)
    db.flush()
    audit.record(db, action="CREATE", entity="procurement_event", entity_id=e.id, user=p.user, after=body.model_dump(), request=request)
    db.commit()
    return event_out(db, load_event(db, e.id), p)


@router.get("/{eid}")
def get_event(eid: uuid.UUID, p: Principal = Depends(require("src:view")), db: Session = Depends(get_db)):
    e = load_event(db, eid)
    _officer_scope(db, p, e)
    return event_out(db, e, p)


@router.put("/{eid}")
def update_event(eid: uuid.UUID, body: EventUpdateIn, request: Request, p: Principal = Depends(require("src:edit")),
                 db: Session = Depends(get_db)):
    e = load_event(db, eid)
    _officer_scope(db, p, e, "src:edit")
    if e.status != EventStatus.draft:
        raise AppError(409, "LOCKED", "Published events can only be changed through a formal amendment.")
    data = body.model_dump(exclude_none=True)
    for k in ("title", "description", "eligibility", "closes_at", "clarification_deadline", "required_docs",
              "contract_start", "contract_end", "is_public"):
        if k in data:
            setattr(e, k, data[k])
    if body.technical_weight is not None:
        e.technical_weight, e.financial_weight = body.technical_weight, 100 - body.technical_weight
    if body.criteria is not None:
        e.criteria = [c.model_dump() for c in body.criteria]
    lots = {str(lt.id): lt for lt in e.lots}
    for k, v in (body.specifications or {}).items():
        if k in lots:
            lots[k].specification = v
    for k, v in (body.delivery_windows or {}).items():
        if k in lots:
            lots[k].delivery_window = v
    _validate_weights(e)
    e.updated_by = p.id
    audit.record(db, action="UPDATE", entity="procurement_event", entity_id=e.id, user=p.user,
                 after={k: str(v) for k, v in data.items()}, request=request)
    db.commit()
    return event_out(db, load_event(db, e.id), p)


# ---------------------------------------------------------------- approval & publication
@router.post("/{eid}/submit")
def submit(eid: uuid.UUID, request: Request, p: Principal = Depends(require("src:submit")), db: Session = Depends(get_db)):
    e = load_event(db, eid)
    _officer_scope(db, p, e, "src:submit")
    if e.status != EventStatus.draft:
        raise AppError(409, "INVALID_TRANSITION", "Only draft events can be submitted.")
    if not e.lots:
        raise AppError(422, "NO_LOTS", "Add at least one lot.")
    if as_utc(e.closes_at) <= utcnow() + timedelta(hours=1):
        raise AppError(422, "VALIDATION_ERROR", "Move the closing time further into the future before submitting.")
    _validate_weights(e)
    e.status = EventStatus.pending_approval
    wf.start(db, "sourcing_event", entity="procurement_event", entity_id=e.id, entity_ref=e.reference,
             title=f"Publish {e.reference}: {e.title}", scope_org_id=e.county_id, initiator=p,
             amount=float(e.estimated_value or 0))
    audit.record(db, action="SUBMIT", entity="procurement_event", entity_id=e.id, user=p.user, request=request)
    db.commit()
    return event_out(db, e, p)


def eligible_suppliers(db: Session, e: ProcurementEvent) -> list[Supplier]:
    rows = db.scalars(select(Supplier).options(selectinload(Supplier.documents)).where(
        Supplier.status.in_([SupplierStatus.prequalified, SupplierStatus.active]))).all()
    return [s for s in rows if not ev_svc.eligibility(e, s)]


def _published(db, inst, p, note_):
    e = load_event(db, inst.entity_id)
    e.status, e.opens_at = EventStatus.open, utcnow()
    for s in eligible_suppliers(db, e):
        note.to_users(db, note.users_of_org(db, s.organization_id), f"New opportunity: {e.reference}",
                      f"{e.title}. Closes {as_utc(e.closes_at):%d %b %Y %H:%M} UTC.", f"/app/opportunities/{e.id}",
                      "opportunity", sms=True)


def _event_back(db, inst, p, note_):
    db.get(ProcurementEvent, inst.entity_id).status = EventStatus.draft


wf.DEFINITIONS["sourcing_event"].hooks.update(complete=_published, reject=_event_back, **{"return": _event_back})


# ---------------------------------------------------------------- clarifications & amendments
class AnswerIn(BaseModel):
    answer: str = Field(min_length=3)


class AmendIn(BaseModel):
    closes_at: datetime
    note: str = Field(min_length=10)


def bidders(db, e) -> list[uuid.UUID]:
    sup = db.scalars(select(Supplier.organization_id).join(Bid, Bid.supplier_id == Supplier.id).where(Bid.event_id == e.id)).all()
    return [u for o in sup for u in note.users_of_org(db, o)]


@router.get("/{eid}/clarifications")
def clarifications(eid: uuid.UUID, p: Principal = Depends(require("src:view")), db: Session = Depends(get_db)):
    e = load_event(db, eid)
    _officer_scope(db, p, e)
    rows = db.scalars(select(Clarification).where(Clarification.event_id == e.id).order_by(Clarification.created_at)).all()
    sup = {s.id: s.legal_name for s in db.scalars(select(Supplier).where(Supplier.id.in_([r.supplier_id for r in rows if r.supplier_id])))}
    return [{"id": c.id, "kind": c.kind, "question": c.question, "answer": c.answer, "asked_by": sup.get(c.supplier_id),
             "created_at": c.created_at, "answered_at": c.answered_at} for c in rows]


@router.post("/clarifications/{cid}/answer")
def answer(cid: uuid.UUID, body: AnswerIn, request: Request, p: Principal = Depends(require("src:edit")), db: Session = Depends(get_db)):
    c = db.get(Clarification, cid)
    if c is None:
        raise AppError(404, "NOT_FOUND", "Question not found.")
    e = load_event(db, c.event_id)
    _officer_scope(db, p, e, "src:edit")
    c.answer, c.answered_by, c.answered_at = body.answer, p.id, utcnow()
    # answers are shared with every bidder / eligible supplier (fair access)
    users = bidders(db, e) + [u for s in eligible_suppliers(db, e) for u in note.users_of_org(db, s.organization_id)]
    note.to_users(db, users, f"Clarification published: {e.reference}", c.question[:120], f"/app/opportunities/{e.id}", "clarification")
    audit.record(db, action="ANSWER", entity="clarification", entity_id=c.id, user=p.user, request=request)
    db.commit()
    return {"id": c.id, "answer": c.answer}


@router.post("/{eid}/amend")
def amend(eid: uuid.UUID, body: AmendIn, request: Request, p: Principal = Depends(require("src:edit")), db: Session = Depends(get_db)):
    """BR-011: changes after publication are formal amendments, recorded and sent to everyone concerned."""
    e = load_event(db, eid)
    _officer_scope(db, p, e, "src:edit")
    if e.status != EventStatus.open:
        raise AppError(409, "INVALID_TRANSITION", "Only open events can be amended.")
    if as_utc(body.closes_at) <= utcnow():
        raise AppError(422, "VALIDATION_ERROR", "The new closing time must be in the future.")
    before = e.closes_at
    e.closes_at = body.closes_at
    db.add(Clarification(event_id=e.id, kind="amendment", question=f"Closing time changed to {as_utc(body.closes_at):%d %b %Y %H:%M} UTC",
                         answer=body.note, answered_by=p.id, answered_at=utcnow()))
    users = bidders(db, e) + [u for s in eligible_suppliers(db, e) for u in note.users_of_org(db, s.organization_id)]
    note.to_users(db, users, f"Amendment: {e.reference}", body.note, f"/app/opportunities/{e.id}", "amendment", sms=True)
    audit.record(db, action="AMEND", entity="procurement_event", entity_id=e.id, user=p.user,
                 before={"closes_at": before}, after={"closes_at": body.closes_at}, reason=body.note, request=request)
    db.commit()
    return event_out(db, e, p)


# ---------------------------------------------------------------- opening
@router.post("/{eid}/open")
def open_bids(eid: uuid.UUID, request: Request, p: Principal = Depends(require("src:edit")), db: Session = Depends(get_db)):
    """Formal bid opening after closing. Decrypts each sealed bid, verifies its checksum, records an opening register."""
    e = load_event(db, eid)
    _officer_scope(db, p, e, "src:edit")
    if e.status != EventStatus.closed:
        raise AppError(409, "NOT_CLOSED", "Bids can only be opened after the event has closed.")
    bids = db.scalars(select(Bid).options(selectinload(Bid.supplier)).where(Bid.event_id == e.id,
                                                                            Bid.status == BidStatus.submitted)).all()
    register = []
    for b in bids:
        b.opened_payload = sealing.unseal(b.sealed_payload, b.payload_sha256)
        b.status = BidStatus.opened
        register.append({"supplier": b.supplier.legal_name, "submitted_at": b.submitted_at, "lots": b.lots_bid,
                         "sha256": b.payload_sha256[:12]})
    e.status, e.opened_at, e.opened_by = EventStatus.under_evaluation, utcnow(), p.id
    audit.record(db, action="OPEN_BIDS", entity="procurement_event", entity_id=e.id, user=p.user,
                 after={"register": register}, request=request)
    db.commit()
    return {"register": register, "event": event_out(db, e, p)}


@router.get("/{eid}/bids")
def list_bids(eid: uuid.UUID, p: Principal = Depends(require("src:view")), db: Session = Depends(get_db)):
    e = load_event(db, eid)
    _officer_scope(db, p, e)
    bids = db.scalars(select(Bid).options(selectinload(Bid.supplier)).where(Bid.event_id == e.id,
                                                                            Bid.status != BidStatus.draft)).all()
    opened = e.opened_at is not None
    if not opened:
        audit.record(db, action="VIEW_SEALED", entity="procurement_event", entity_id=e.id, user=p.user)
        db.commit()
    return {"opened": opened, "bids": [{
        "id": b.id, "supplier": b.supplier.legal_name, "status": b.status.value, "submitted_at": b.submitted_at,
        "revision": b.revision, "lots_bid": b.lots_bid, "sha256": b.payload_sha256[:12],
        "contents": b.opened_payload if opened else None} for b in bids]}


# ---------------------------------------------------------------- evaluation panel
class AssignIn(BaseModel):
    user_ids: list[uuid.UUID]


@router.get("/{eid}/evaluators")
def evaluators(eid: uuid.UUID, p: Principal = Depends(require("src:view")), db: Session = Depends(get_db)):
    e = load_event(db, eid)
    _officer_scope(db, p, e)
    rows = db.scalars(select(EvaluationAssignment).options(selectinload(EvaluationAssignment.user))
                      .where(EvaluationAssignment.event_id == e.id)).all()
    cands = db.scalars(select(User).join(UserRole, UserRole.user_id == User.id).join(Role, Role.id == UserRole.role_id)
                       .where(Role.key == "evaluation_committee_member", UserRole.is_active)).unique().all()
    return {"assigned": [{"user_id": a.user_id, "name": a.user.full_name, "coi_declared": a.coi_declared_at is not None,
                          "has_conflict": a.has_conflict, "submitted": a.submitted_at is not None} for a in rows],
            "candidates": [{"id": u.id, "name": u.full_name} for u in cands]}


@router.post("/{eid}/evaluators")
def assign(eid: uuid.UUID, body: AssignIn, request: Request, p: Principal = Depends(require("src:edit")), db: Session = Depends(get_db)):
    e = load_event(db, eid)
    _officer_scope(db, p, e, "src:edit")
    if e.status in (EventStatus.evaluated, EventStatus.approved, EventStatus.awarded, EventStatus.cancelled):
        raise AppError(409, "LOCKED", "The panel can no longer be changed.")
    if p.id in body.user_ids or (e.created_by and e.created_by in body.user_ids):
        raise AppError(409, "SOD_CONFLICT", "The officer who created this event cannot sit on its evaluation panel (SoD-02).")
    have = {a.user_id for a in db.scalars(select(EvaluationAssignment).where(EvaluationAssignment.event_id == e.id))}
    for uid in body.user_ids:
        u = db.get(User, uid)
        if u is None or "evaluation_committee_member" not in {ur.role.key for ur in u.roles if ur.is_active}:
            raise AppError(422, "VALIDATION_ERROR", "Only Evaluation Committee Members can be assigned.")
        if uid not in have:
            db.add(EvaluationAssignment(event_id=e.id, user_id=uid, created_by=p.id))
    note.to_users(db, [u for u in body.user_ids if u not in have], f"Evaluation assigned: {e.reference}",
                  "Declare any conflict of interest before bids are shown to you.", f"/app/evaluations/{e.id}", "evaluation")
    audit.record(db, action="ASSIGN_PANEL", entity="procurement_event", entity_id=e.id, user=p.user,
                 after={"evaluators": [str(u) for u in body.user_ids]}, request=request)
    db.commit()
    return evaluators(eid, p, db)


@router.post("/{eid}/consolidate")
def consolidate(eid: uuid.UUID, request: Request, p: Principal = Depends(require("src:edit")), db: Session = Depends(get_db)):
    from app.core.config import settings
    e = load_event(db, eid)
    _officer_scope(db, p, e, "src:edit")
    if e.status not in (EventStatus.under_evaluation, EventStatus.evaluated):
        raise AppError(409, "INVALID_TRANSITION", "Open the bids first.")
    assigns = db.scalars(select(EvaluationAssignment).options(selectinload(EvaluationAssignment.user))
                         .where(EvaluationAssignment.event_id == e.id)).all()
    done = [a for a in assigns if a.submitted_at and not a.has_conflict]
    pending = [a.user.full_name for a in assigns if not a.submitted_at and not a.has_conflict]
    if len(done) < settings.bid_min_evaluators or pending:
        raise AppError(409, "EVALUATION_INCOMPLETE",
                       "Waiting for evaluators: " + (", ".join(pending) if pending else f"at least {settings.bid_min_evaluators} needed") + ".")
    bids = db.scalars(select(Bid).options(selectinload(Bid.supplier).selectinload(Supplier.documents))
                      .where(Bid.event_id == e.id, Bid.status == BidStatus.opened)).all()
    e.results = ev_svc.consolidate(e, bids, list(assigns))
    e.status = EventStatus.evaluated
    audit.record(db, action="CONSOLIDATE", entity="procurement_event", entity_id=e.id, user=p.user,
                 after={"recommended_total": e.results["recommended_total"]}, request=request)
    db.commit()
    return event_out(db, e, p)


@router.post("/{eid}/recommend")
def recommend(eid: uuid.UUID, request: Request, p: Principal = Depends(require("src:submit")), db: Session = Depends(get_db)):
    """Submit the evaluation report + award recommendation for commitment check and approval."""
    e = load_event(db, eid)
    _officer_scope(db, p, e, "src:submit")
    if e.status != EventStatus.evaluated or not e.results:
        raise AppError(409, "INVALID_TRANSITION", "Consolidate the evaluation first.")
    if not any(lo["recommended"] for lo in e.results["lots"]):
        raise AppError(409, "NO_RESPONSIVE_BIDS", "No lot has a responsive bid. Cancel or re-advertise the event.")
    for lo in e.results["lots"]:
        if lo["recommended"]:
            r = next(b for b in lo["bids"] if b["bid_id"] == lo["recommended"])
            db.add(Award(event_id=e.id, lot_id=uuid.UUID(lo["lot_id"]), bid_id=uuid.UUID(r["bid_id"]),
                         supplier_id=uuid.UUID(r["supplier_id"]), quantity=Decimal(lo["quantity"]),
                         unit_price=Decimal(r["unit_price"]), value=Decimal(r["value"]), score=Decimal(str(r["total"])),
                         created_by=p.id))
    e.status = EventStatus.approved
    wf.start(db, "award", entity="procurement_event", entity_id=e.id, entity_ref=e.reference,
             title=f"Award {e.reference}: KSh {Decimal(e.results['recommended_total']):,.0f}", scope_org_id=e.county_id,
             initiator=p, amount=float(e.results["recommended_total"]))
    audit.record(db, action="RECOMMEND", entity="procurement_event", entity_id=e.id, user=p.user,
                 after={"total": e.results["recommended_total"]}, request=request)
    db.commit()
    return event_out(db, e, p)


def _plan_line(db, e) -> BudgetLine | None:
    pl = db.get(ProcurementPlan, e.plan_id) if e.plan_id else None
    return db.get(BudgetLine, pl.budget_line_id) if pl and pl.budget_line_id else None


def _award_budget_check(db, inst, p, note_):
    """Commitment check (stage 1): award total must fit available budget + the plan's own earmark."""
    e = db.get(ProcurementEvent, inst.entity_id)
    bl = _plan_line(db, e)
    if bl is None:
        raise AppError(409, "NO_BUDGET", "This event is not linked to a funded plan.")
    from app.models import Commitment, CommitmentStatus
    earmark = db.scalar(select(func.coalesce(func.sum(Commitment.amount), 0)).where(
        Commitment.source_entity == "procurement_plan", Commitment.source_id == e.plan_id,
        Commitment.status == CommitmentStatus.held)) or 0
    avail = budget.status(db, bl)["available"] + Decimal(earmark)
    total = Decimal(e.results["recommended_total"])
    if total > avail:
        raise AppError(409, "BUDGET_EXCEEDED", f"Award total KSh {total:,.0f} exceeds available budget KSh {avail:,.0f}.")


def _award_done(db, inst, p, note_):
    """Award approved → contracts (+ PO for purchase contracts), budget converted from plan earmark to contracts,
    suppliers notified, public award notice."""
    e = load_event(db, inst.entity_id)
    awards = db.scalars(select(Award).options(selectinload(Award.lot), selectinload(Award.supplier))
                        .where(Award.event_id == e.id, Award.status == AwardStatus.proposed)).all()
    bl = _plan_line(db, e)
    if e.plan_id:
        budget.release(db, "procurement_plan", e.plan_id)
    by_sup: dict[uuid.UUID, list[Award]] = {}
    for a in awards:
        a.status = AwardStatus.approved
        by_sup.setdefault(a.supplier_id, []).append(a)
    now = utcnow()
    kind = ContractKind.framework if e.method == ProcurementMethod.framework else ContractKind.purchase
    names = []
    n_con = db.scalar(select(func.count()).select_from(Contract)) or 0
    n_po = db.scalar(select(func.count()).select_from(PurchaseOrder)) or 0
    for sid, alist in by_sup.items():
        n_con += 1
        total = sum((a.value for a in alist), Decimal(0))
        c = Contract(reference=f"CON-{now:%Y}-{n_con:04d}", event_id=e.id, supplier_id=sid, county_id=e.county_id,
                     budget_line_id=bl.id if bl else None, kind=kind, value=total,
                     starts_on=e.contract_start or now.date(), ends_on=e.contract_end or (now + timedelta(days=90)).date(),
                     created_by=p.id)
        for a in alist:
            c.lines.append(ContractLine(lot_id=a.lot_id, commodity_code=a.lot.commodity_code, unit=a.lot.unit,
                                        quantity=a.quantity, unit_price=a.unit_price))
        db.add(c)
        db.flush()
        if bl:
            budget.commit(db, bl, amount=total, source_entity="contract", source_id=c.id, source_ref=c.reference, actor_id=p.id)
        if kind == ContractKind.purchase:   # one PO for the full quantity
            n_po += 1
            po = PurchaseOrder(reference=f"PO-{now:%Y}-{n_po:05d}", contract_id=c.id, supplier_id=sid, county_id=e.county_id,
                               total=total, issued_at=now, delivery_window=alist[0].lot.delivery_window, created_by=p.id)
            for cl, a in zip(c.lines, alist):
                cl.quantity_ordered = cl.quantity
                po.lines.append(POLine(contract_line_id=cl.id, commodity_code=cl.commodity_code, unit=cl.unit,
                                       quantity=cl.quantity, unit_price=cl.unit_price, schools=a.lot.schools))
            db.add(po)
        sup = alist[0].supplier
        names.append(sup.legal_name)
        note.to_users(db, note.users_of_org(db, sup.organization_id), f"You have been awarded: {e.reference}",
                      f"{len(alist)} lot(s), KSh {total:,.0f}. Contract {c.reference}.", "/app/orders", "award", sms=True)
    for b in db.scalars(select(Bid).options(selectinload(Bid.supplier)).where(Bid.event_id == e.id, Bid.status == BidStatus.opened)):
        won = b.supplier_id in by_sup
        b.status = BidStatus.awarded if won else BidStatus.unsuccessful
        if not won:
            note.to_users(db, note.users_of_org(db, b.supplier.organization_id), f"Outcome: {e.reference}",
                          "Your bid was not successful. You may request a clarification within 7 days.",
                          f"/app/opportunities/{e.id}", "award", sms=True)
    e.status, e.awarded_at = EventStatus.awarded, now
    e.awarded_to = ", ".join(sorted(set(names)))[:300]
    e.awarded_value = sum((a.value for a in awards), Decimal(0))
    if e.plan_id:
        pl = db.get(ProcurementPlan, e.plan_id)
        pl.status = PlanStatus.closed


def _award_back(db, inst, p, note_):
    e = db.get(ProcurementEvent, inst.entity_id)
    for a in db.scalars(select(Award).where(Award.event_id == e.id, Award.status == AwardStatus.proposed)):
        a.status = AwardStatus.cancelled
    e.status = EventStatus.evaluated


wf.DEFINITIONS["award"].hooks.update(advance=_award_budget_check, complete=_award_done, reject=_award_back,
                                     **{"return": _award_back})


@router.post("/{eid}/cancel")
def cancel_event(eid: uuid.UUID, body: AnswerIn, request: Request, p: Principal = Depends(require("src:edit")),
                 db: Session = Depends(get_db)):
    e = load_event(db, eid)
    _officer_scope(db, p, e, "src:edit")
    if e.status in (EventStatus.awarded, EventStatus.cancelled, EventStatus.approved):
        raise AppError(409, "INVALID_TRANSITION", "This event can no longer be cancelled.")
    e.status = EventStatus.cancelled
    note.to_users(db, bidders(db, e), f"Cancelled: {e.reference}", body.answer, f"/app/opportunities/{e.id}", "cancel", sms=True)
    if e.plan_id:
        db.get(ProcurementPlan, e.plan_id).status = PlanStatus.approved
    audit.record(db, action="CANCEL", entity="procurement_event", entity_id=e.id, user=p.user, reason=body.answer, request=request)
    db.commit()
    return event_out(db, e, p)
