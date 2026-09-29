"""Budgets, commitments and exceptions (FR-BUD-01…07)."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, ensure_in_scope, require, scope_for
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import (BudgetException, BudgetLine, Commitment, ExceptionStatus, FundingSource, Organization,
                        ProcurementPlan)
from app.services import audit, budget, workflow as wf

router = APIRouter(tags=["budget"])


class FundingIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str
    kind: str = "grant"


class LineIn(BaseModel):
    code: str = Field(min_length=2, max_length=60)
    name: str
    funding_source_id: uuid.UUID
    org_id: uuid.UUID
    term_id: uuid.UUID | None = None
    category: str = ""
    period_start: date
    period_end: date
    approved_amount: Decimal = Field(gt=0)
    alert_threshold_pct: int = Field(default=80, ge=10, le=100)


class ExceptionIn(BaseModel):
    plan_id: uuid.UUID
    justification: str = Field(min_length=20)


def _line_out(db: Session, bl: BudgetLine) -> dict:
    return {"id": bl.id, "code": bl.code, "name": bl.name, "funding_source": bl.funding_source.name if bl.funding_source else None,
            "funding_source_id": bl.funding_source_id, "org_id": bl.org_id, "org": bl.org.name if bl.org else None,
            "term_id": bl.term_id, "category": bl.category, "period_start": bl.period_start, "period_end": bl.period_end,
            "currency": bl.currency, "alert_threshold_pct": bl.alert_threshold_pct, "is_active": bl.is_active,
            **budget.status(db, bl)}


@router.get("/funding-sources")
def funding_sources(p: Principal = Depends(require("bud:view")), db: Session = Depends(get_db)):
    return [{"id": f.id, "code": f.code, "name": f.name, "kind": f.kind} for f in db.scalars(select(FundingSource).order_by(FundingSource.name))]


@router.post("/funding-sources", status_code=201)
def create_funding(body: FundingIn, request: Request, p: Principal = Depends(require("bud:create")), db: Session = Depends(get_db)):
    if db.scalar(select(FundingSource).where(FundingSource.code == body.code)):
        raise AppError(409, "CODE_IN_USE", "This code is already used.")
    f = FundingSource(**body.model_dump(), created_by=p.id)
    db.add(f)
    db.flush()
    audit.record(db, action="CREATE", entity="funding_source", entity_id=f.id, user=p.user, after=body.model_dump(), request=request)
    db.commit()
    return {"id": f.id, "code": f.code, "name": f.name, "kind": f.kind}


@router.get("/budget-lines")
def lines(p: Principal = Depends(require("bud:view")), db: Session = Depends(get_db)):
    stmt = select(BudgetLine).where(BudgetLine.is_active)
    allowed = scope_for(db, p, "bud:view")
    if allowed is not None:
        stmt = stmt.where(BudgetLine.org_id.in_(allowed))
    return [_line_out(db, bl) for bl in db.scalars(stmt.order_by(BudgetLine.name))]


@router.post("/budget-lines", status_code=201)
def create_line(body: LineIn, request: Request, p: Principal = Depends(require("bud:create")), db: Session = Depends(get_db)):
    ensure_in_scope(db, p, "bud:create", body.org_id)
    if body.period_end <= body.period_start:
        raise AppError(422, "VALIDATION_ERROR", "The period must end after it starts.")
    if db.scalar(select(BudgetLine).where(BudgetLine.code == body.code)):
        raise AppError(409, "CODE_IN_USE", "This budget code is already used.")
    if db.get(FundingSource, body.funding_source_id) is None or db.get(Organization, body.org_id) is None:
        raise AppError(422, "VALIDATION_ERROR", "Unknown funding source or organisation.")
    bl = BudgetLine(**body.model_dump(), created_by=p.id)
    db.add(bl)
    db.flush()
    audit.record(db, action="CREATE", entity="budget_line", entity_id=bl.id, user=p.user, after=body.model_dump(), request=request)
    db.commit()
    return _line_out(db, db.get(BudgetLine, bl.id))


@router.get("/budget-lines/{lid}")
def line_detail(lid: uuid.UUID, p: Principal = Depends(require("bud:view")), db: Session = Depends(get_db)):
    bl = db.get(BudgetLine, lid)
    if bl is None:
        raise AppError(404, "NOT_FOUND", "Budget line not found.")
    ensure_in_scope(db, p, "bud:view", bl.org_id)
    cms = db.scalars(select(Commitment).where(Commitment.budget_line_id == bl.id).order_by(Commitment.created_at.desc())).all()
    return {**_line_out(db, bl), "commitments": [
        {"id": c.id, "source": c.source_entity, "ref": c.source_ref, "amount": c.amount, "status": c.status.value,
         "created_at": c.created_at, "with_exception": c.exception_id is not None} for c in cms]}


@router.get("/budget-exceptions")
def exceptions(p: Principal = Depends(require("bud:view")), db: Session = Depends(get_db)):
    rows = db.scalars(select(BudgetException).order_by(BudgetException.created_at.desc())).all()
    allowed = scope_for(db, p, "bud:view")
    out = []
    for e in rows:
        if allowed is not None and e.budget_line.org_id not in allowed:
            continue
        inst = wf.active_for(db, "budget_exception", e.id)
        out.append({"id": e.id, "line": e.budget_line.name, "source_ref": e.source_ref, "requested_amount": e.requested_amount,
                    "shortfall": e.shortfall, "justification": e.justification, "status": e.status.value,
                    "decision_note": e.decision_note, "created_at": e.created_at,
                    "workflow": wf.serialize(inst, p, db) if inst else None})
    return out


@router.post("/budget-exceptions", status_code=201)
def request_exception(body: ExceptionIn, request: Request, p: Principal = Depends(require("bud:submit")),
                      db: Session = Depends(get_db)):
    pl = db.get(ProcurementPlan, body.plan_id)
    if pl is None or not pl.budget_line_id:
        raise AppError(422, "VALIDATION_ERROR", "The plan must have a budget line first.")
    bl = db.get(BudgetLine, pl.budget_line_id)
    ensure_in_scope(db, p, "bud:submit", bl.org_id)
    chk = budget.check(db, bl, pl.estimated_value)
    if chk["sufficient"]:
        raise AppError(409, "NOT_NEEDED", "The budget is sufficient; no exception is needed.")
    if db.scalar(select(BudgetException).where(BudgetException.source_id == pl.id, BudgetException.status == ExceptionStatus.pending)):
        raise AppError(409, "ALREADY_REQUESTED", "An exception request is already pending for this plan.")
    e = BudgetException(budget_line_id=bl.id, source_entity="procurement_plan", source_id=pl.id, source_ref=pl.reference,
                        requested_amount=pl.estimated_value, shortfall=chk["shortfall"], justification=body.justification,
                        created_by=p.id)
    db.add(e)
    db.flush()
    wf.start(db, "budget_exception", entity="budget_exception", entity_id=e.id, entity_ref=pl.reference,
             title=f"Budget exception · {pl.reference} · shortfall KSh {chk['shortfall']:,.0f}", scope_org_id=bl.org_id,
             initiator=p, amount=float(chk["shortfall"]))
    audit.record(db, action="REQUEST", entity="budget_exception", entity_id=e.id, user=p.user,
                 after={"shortfall": chk["shortfall"], "plan": pl.reference}, reason=body.justification, request=request)
    db.commit()
    return {"id": e.id, "status": e.status.value, "shortfall": e.shortfall}


def _exc_decide(status):
    def hook(db, inst, p, note):
        e = db.get(BudgetException, inst.entity_id)
        e.status, e.decided_by, e.decided_at, e.decision_note = status, p.id, utcnow(), note
    return hook


wf.DEFINITIONS["budget_exception"].hooks.update(complete=_exc_decide(ExceptionStatus.approved),
                                                reject=_exc_decide(ExceptionStatus.rejected),
                                                **{"return": _exc_decide(ExceptionStatus.rejected)})
