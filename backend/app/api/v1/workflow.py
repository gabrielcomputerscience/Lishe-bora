"""Approval inbox and actions — one place for every approval type (FR-PLT-01)."""
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, current_principal, scope_any
from app.core.errors import AppError
from app.models import InstanceStatus, WorkflowInstance
from app.services import audit, workflow as wf

router = APIRouter(prefix="/workflow", tags=["approvals"])

LINKS = {"procurement_event": "/app/sourcing/{id}", "school_demand": "/app/demand/{id}", "procurement_plan": "/app/plans/{id}",
         "budget_exception": "/app/budgets?exception={id}", "menu": "/app/menus?id={id}",
         "stock_movement": "/app/inventory?movement={id}", "stock_count": "/app/inventory?count={id}",
         "invoice": "/app/invoices/{id}"}


class ActIn(BaseModel):
    action: str
    note: str = ""


@router.get("/inbox")
def inbox(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Items waiting for *this* user: permission + scope + segregation-of-duties all satisfied."""
    rows = db.scalars(select(WorkflowInstance).options(selectinload(WorkflowInstance.actions))
                      .where(WorkflowInstance.status == InstanceStatus.active)
                      .order_by(WorkflowInstance.stage_due_at)).all()
    mine, submitted = [], []
    for inst in rows:
        ok, _ = wf.can_act(db, p, inst)
        if ok:
            mine.append({**wf.serialize(inst), "link": LINKS.get(inst.entity, "").format(id=inst.entity_id)})
        elif inst.initiator_id == p.id:
            submitted.append({**wf.serialize(inst), "link": LINKS.get(inst.entity, "").format(id=inst.entity_id)})
    return {"waiting_for_me": mine, "submitted_by_me": submitted}


@router.post("/{iid}/act")
def act(iid: uuid.UUID, body: ActIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    inst = db.get(WorkflowInstance, iid)
    if inst is None:
        raise AppError(404, "NOT_FOUND", "Approval not found.")
    stage = wf.current_stage(inst).key if inst.status == InstanceStatus.active else ""
    wf.act(db, inst, p, body.action, body.note)
    audit.record(db, action=body.action.upper(), entity=inst.entity, entity_id=inst.entity_id, user=p.user,
                 after={"workflow": inst.definition, "stage": stage, "status": inst.status.value}, reason=body.note,
                 request=request)
    db.commit()
    return wf.serialize(inst, p, db)


@router.post("/{iid}/cancel")
def cancel(iid: uuid.UUID, body: ActIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    inst = db.get(WorkflowInstance, iid)
    if inst is None or inst.status != InstanceStatus.active:
        raise AppError(404, "NOT_FOUND", "Active approval not found.")
    wf.cancel(db, inst, p, body.note)
    hook = wf.DEFINITIONS[inst.definition].hooks.get("return")
    if hook:
        hook(db, inst, p, body.note or "Withdrawn")
    audit.record(db, action="WITHDRAW", entity=inst.entity, entity_id=inst.entity_id, user=p.user, request=request)
    db.commit()
    return wf.serialize(inst, p, db)


@router.get("/for/{entity}/{entity_id}")
def for_entity(entity: str, entity_id: uuid.UUID, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Latest approval for a record (used by pages that open from the approvals inbox)."""
    inst = db.scalar(select(WorkflowInstance).options(selectinload(WorkflowInstance.actions))
                     .where(WorkflowInstance.entity == entity, WorkflowInstance.entity_id == entity_id)
                     .order_by(WorkflowInstance.started_at.desc()).limit(1))
    if inst is None:
        raise AppError(404, "NOT_FOUND", "No approval for this record.")
    visible = scope_any(db, p, *p.grants)
    if inst.initiator_id != p.id and visible is not None and inst.scope_org_id not in visible:
        raise AppError(403, "OUT_OF_SCOPE", "This record is outside your assigned area.")
    return {**wf.serialize(inst, p, db), "link": LINKS.get(inst.entity, "").format(id=inst.entity_id)}
