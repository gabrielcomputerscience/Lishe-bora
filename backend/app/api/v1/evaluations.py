"""Evaluator workspace: COI declaration gates access to bids; individual scores; submit (FR-PRO-07/08)."""
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, require
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import Bid, BidStatus, EvaluationAssignment, EventStatus, ProcurementEvent, Supplier
from app.api.v1.procurement import event_out, load_event
from app.services import audit, evaluation as ev_svc

router = APIRouter(prefix="/evaluations", tags=["evaluation"])


class CoiIn(BaseModel):
    has_conflict: bool
    statement: str = Field(min_length=10)


class ScoresIn(BaseModel):
    scores: dict[str, dict[str, float | str]]   # {bid_id: {criterion: score, "_comment": "..."}}


def _mine(db, p: Principal, eid) -> EvaluationAssignment:
    a = db.scalar(select(EvaluationAssignment).where(EvaluationAssignment.event_id == eid, EvaluationAssignment.user_id == p.id))
    if a is None:
        raise AppError(403, "NOT_ASSIGNED", "You are not on the evaluation panel for this event.")
    return a


@router.get("")
def my_evaluations(p: Principal = Depends(require("eva:evaluate")), db: Session = Depends(get_db)):
    rows = db.scalars(select(EvaluationAssignment).where(EvaluationAssignment.user_id == p.id)).all()
    out = []
    for a in rows:
        e = db.get(ProcurementEvent, a.event_id)
        out.append({"event_id": e.id, "reference": e.reference, "title": e.title, "status": e.status.value,
                    "coi_declared": a.coi_declared_at is not None, "has_conflict": a.has_conflict,
                    "submitted": a.submitted_at is not None})
    return out


@router.get("/{eid}")
def workspace(eid: uuid.UUID, p: Principal = Depends(require("eva:evaluate")), db: Session = Depends(get_db)):
    a = _mine(db, p, eid)
    e = load_event(db, eid)
    base = {"event": {k: v for k, v in event_out(db, e, officer=False).items() if k != "estimated_value"},
            "assignment": {"coi_declared": a.coi_declared_at is not None, "has_conflict": a.has_conflict,
                           "submitted": a.submitted_at is not None, "scores": a.scores}}
    if a.coi_declared_at is None or a.has_conflict or e.opened_at is None:
        base["bids"] = None      # hidden until COI declared (and bids formally opened)
        return base
    bids = db.scalars(select(Bid).options(selectinload(Bid.supplier).selectinload(Supplier.documents))
                      .where(Bid.event_id == e.id, Bid.status.in_([BidStatus.opened, BidStatus.awarded, BidStatus.unsuccessful]))).all()
    base["bids"] = [{"id": b.id, "supplier": b.supplier.legal_name, "supplier_type": b.supplier.supplier_type.value,
                     "inclusion_verified": b.supplier.inclusion_verified, "eligibility_issues": ev_svc.eligibility(e, b.supplier),
                     "auto_scores": ev_svc.auto_scores(e, b.supplier), "contents": b.opened_payload} for b in bids]
    audit.record(db, action="VIEW_BIDS", entity="procurement_event", entity_id=e.id, user=p.user)
    db.commit()
    return base


@router.post("/{eid}/coi")
def declare(eid: uuid.UUID, body: CoiIn, request: Request, p: Principal = Depends(require("eva:evaluate")), db: Session = Depends(get_db)):
    """BR-015: mandatory before any bid is visible. A declared conflict removes the evaluator from scoring."""
    a = _mine(db, p, eid)
    if a.coi_declared_at:
        raise AppError(409, "ALREADY_DECLARED", "You have already made your declaration.")
    a.coi_declared_at, a.has_conflict, a.coi_statement = utcnow(), body.has_conflict, body.statement
    audit.record(db, action="DECLARE_COI", entity="procurement_event", entity_id=eid, user=p.user,
                 after={"has_conflict": body.has_conflict}, reason=body.statement, request=request)
    db.commit()
    return {"has_conflict": a.has_conflict}


@router.put("/{eid}/scores")
def save_scores(eid: uuid.UUID, body: ScoresIn, p: Principal = Depends(require("eva:evaluate")), db: Session = Depends(get_db)):
    a = _mine(db, p, eid)
    e = load_event(db, eid)
    if a.coi_declared_at is None or a.has_conflict:
        raise AppError(403, "COI_REQUIRED", "Declare that you have no conflict of interest first.")
    if a.submitted_at or e.status != EventStatus.under_evaluation:
        raise AppError(409, "LOCKED", "Scores can no longer be changed.")
    limits = {c["key"]: float(c["max"]) for c in e.criteria if not c.get("auto")}
    valid_bids = {str(b) for b in db.scalars(select(Bid.id).where(Bid.event_id == e.id, Bid.status == BidStatus.opened))}
    clean = {}
    for bid_id, sc in body.scores.items():
        if bid_id not in valid_bids:
            raise AppError(422, "VALIDATION_ERROR", "Unknown bid.")
        row = {}
        for k, v in sc.items():
            if k == "_comment":
                row[k] = str(v)[:1000]
                continue
            if k not in limits:
                raise AppError(422, "VALIDATION_ERROR", f"Unknown criterion '{k}'.")
            v = float(v)
            if not 0 <= v <= limits[k]:
                raise AppError(422, "VALIDATION_ERROR", f"Score for '{k}' must be between 0 and {limits[k]:g}.")
            row[k] = v
        clean[bid_id] = row
    a.scores = clean
    db.commit()
    return {"scores": a.scores}


@router.post("/{eid}/submit")
def submit(eid: uuid.UUID, request: Request, p: Principal = Depends(require("eva:submit")), db: Session = Depends(get_db)):
    a = _mine(db, p, eid)
    e = load_event(db, eid)
    if a.coi_declared_at is None or a.has_conflict:
        raise AppError(403, "COI_REQUIRED", "Declare that you have no conflict of interest first.")
    manual = [c["key"] for c in e.criteria if not c.get("auto")]
    opened = [str(b) for b in db.scalars(select(Bid.id).where(Bid.event_id == e.id, Bid.status == BidStatus.opened))]
    missing = [b for b in opened if any(k not in a.scores.get(b, {}) for k in manual)]
    if missing:
        raise AppError(422, "INCOMPLETE", f"Score every criterion for every bid ({len(missing)} bid(s) incomplete).")
    a.submitted_at = utcnow()
    audit.record(db, action="SUBMIT_SCORES", entity="procurement_event", entity_id=e.id, user=p.user, request=request)
    db.commit()
    return {"submitted": True}
