"""Reusable approval engine (FR-PLT-01, SRS §7.1).

A definition is an ordered list of stages. Each stage names the permission an approver needs, an SLA,
and optional threshold conditions (min_amount/max_amount) so stages can be skipped or routed by value.
Rules enforced for every action:
  • the actor holds the stage permission *within the scope* of the record (data scope)
  • the initiator can never approve their own submission (SoD-01/05)
  • one person may act on only one stage of the same instance (SoD-03, configurable per definition)
Callers register `on_complete` / `on_reject` / `on_return` hooks to move the business record's status."""
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Principal, scope_for
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import InstanceStatus, WorkflowAction, WorkflowInstance


@dataclass
class Stage:
    key: str
    label: str
    permission: str
    sla_days: int = 3
    min_amount: float | None = None      # stage applies only when amount >= min_amount
    max_amount: float | None = None      # stage applies only when amount <= max_amount

    def applies(self, amount: float | None) -> bool:
        if amount is None:
            return self.min_amount is None
        if self.min_amount is not None and amount < self.min_amount:
            return False
        if self.max_amount is not None and amount > self.max_amount:
            return False
        return True


@dataclass
class Definition:
    key: str
    name: str
    stages: list[Stage]
    version: int = 1
    one_stage_per_person: bool = True
    hooks: dict[str, Callable] = field(default_factory=dict)   # complete | reject | return


DEFINITIONS: dict[str, Definition] = {}


def define(d: Definition) -> Definition:
    DEFINITIONS[d.key] = d
    return d


# Thresholds are placeholders until inception decides them (SRS §14 Q3) — see settings key "workflow.thresholds".
define(Definition("menu", "Menu approval", [Stage("nutrition", "Nutrition validation", "dem:verify", 3)]))
define(Definition("school_demand", "School demand approval", [
    Stage("validate", "Validation", "dem:verify", 2),
    Stage("approve", "School approval", "dem:approve", 2),
], one_stage_per_person=False))   # a small school may have one admin who validates and approves
define(Definition("procurement_plan", "Procurement plan approval", [
    Stage("budget", "Budget confirmation", "bud:verify", 2),
    Stage("approve", "County approval", "dem:approve", 3),
]))
define(Definition("sourcing_event", "Sourcing event approval", [
    Stage("approve", "Approval to publish", "src:approve", 2),
]))
define(Definition("award", "Evaluation & award approval", [
    Stage("budget", "Commitment check", "bud:verify", 2),
    Stage("approve", "Award approval", "eva:approve", 3),
]))
define(Definition("stock_adjustment", "Stock adjustment / write-off", [
    Stage("verify", "Stock verification", "inv:verify", 2),
]))
define(Definition("stock_count", "Stock count reconciliation", [
    Stage("verify", "Count verification", "inv:verify", 2),
]))
define(Definition("invoice", "Invoice verification & approval", [
    Stage("verify", "Finance verification (three-way match)", "fin:verify", 2),
    Stage("approve", "Payment approval", "fin:approve", 2),
]))
define(Definition("budget_exception", "Budget exception", [Stage("approve", "Exception approval", "bud:approve", 2)]))


def _stages(defn: Definition, amount) -> list[Stage]:
    return [s for s in defn.stages if s.applies(amount)]


def active_for(db: Session, entity: str, entity_id) -> WorkflowInstance | None:
    return db.scalar(select(WorkflowInstance).where(WorkflowInstance.entity == entity,
                                                    WorkflowInstance.entity_id == entity_id,
                                                    WorkflowInstance.status == InstanceStatus.active))


def _log(inst, stage_key, action, p: Principal | None, note=""):
    inst.actions.append(WorkflowAction(stage_index=inst.stage_index, stage_key=stage_key, action=action,
                                       actor_id=p.id if p else None,
                                       actor_label=(p.user.full_name if p else "system"), note=note, at=utcnow()))


def start(db: Session, definition: str, *, entity: str, entity_id, entity_ref: str, title: str,
          scope_org_id, initiator: Principal, amount: float | None = None, context: dict | None = None) -> WorkflowInstance:
    defn = DEFINITIONS[definition]
    if active_for(db, entity, entity_id):
        raise AppError(409, "ALREADY_IN_WORKFLOW", "This record is already awaiting approval.")
    stages = _stages(defn, amount)
    now = utcnow()
    inst = WorkflowInstance(definition=definition, version=defn.version, entity=entity, entity_id=entity_id,
                            entity_ref=entity_ref, title=title, scope_org_id=scope_org_id, amount=amount,
                            stage_index=0, stage_due_at=now + timedelta(days=stages[0].sla_days),
                            initiator_id=initiator.id, started_at=now, context=context or {})
    db.add(inst)
    _log(inst, "submit", "submit", initiator)
    db.flush()
    return inst


def current_stage(inst: WorkflowInstance) -> Stage:
    return _stages(DEFINITIONS[inst.definition], inst.amount)[inst.stage_index]


def can_act(db: Session, p: Principal, inst: WorkflowInstance) -> tuple[bool, str]:
    if inst.status != InstanceStatus.active:
        return False, "This approval is already finished."
    st = current_stage(inst)
    if not p.can(st.permission):
        return False, f"This step needs the '{st.permission}' permission."
    allowed = scope_for(db, p, st.permission)
    if allowed is not None and inst.scope_org_id not in allowed:
        return False, "This record is outside your assigned area."
    if inst.initiator_id == p.id:
        return False, "You cannot approve something you submitted (segregation of duties)."
    if DEFINITIONS[inst.definition].one_stage_per_person:
        if any(a.actor_id == p.id and a.action == "approve" for a in inst.actions):
            return False, "You already approved an earlier step of this item (segregation of duties)."
    return True, ""


def act(db: Session, inst: WorkflowInstance, p: Principal, action: str, note: str = "") -> WorkflowInstance:
    if action not in ("approve", "reject", "return"):
        raise AppError(422, "VALIDATION_ERROR", "Action must be approve, reject or return.")
    ok, why = can_act(db, p, inst)
    if not ok:
        raise AppError(403, "WORKFLOW_FORBIDDEN", why)
    if action in ("reject", "return") and not note.strip():
        raise AppError(422, "VALIDATION_ERROR", "Please give a reason.")
    defn = DEFINITIONS[inst.definition]
    st = current_stage(inst)
    _log(inst, st.key, action, p, note)
    now = utcnow()
    if action == "approve":
        stages = _stages(defn, inst.amount)
        if inst.stage_index + 1 < len(stages):
            inst.stage_index += 1
            inst.stage_due_at = now + timedelta(days=stages[inst.stage_index].sla_days)
            hook = defn.hooks.get("advance")
        else:
            inst.status, inst.finished_at, inst.stage_due_at = InstanceStatus.approved, now, None
            hook = defn.hooks.get("complete")
    else:
        inst.status = InstanceStatus.rejected if action == "reject" else InstanceStatus.returned
        inst.finished_at, inst.stage_due_at = now, None
        hook = defn.hooks.get(action)
    if hook:
        hook(db, inst, p, note)
    db.flush()
    return inst


def cancel(db: Session, inst: WorkflowInstance, p: Principal, note=""):
    if inst.initiator_id != p.id:
        raise AppError(403, "FORBIDDEN", "Only the person who submitted this can withdraw it.")
    _log(inst, current_stage(inst).key, "cancel", p, note)
    inst.status, inst.finished_at = InstanceStatus.cancelled, utcnow()


def serialize(inst: WorkflowInstance, p: Principal | None = None, db: Session | None = None) -> dict:
    stages = _stages(DEFINITIONS[inst.definition], inst.amount)
    now = utcnow()
    from app.core.timeutil import as_utc
    due = as_utc(inst.stage_due_at)
    out = {
        "id": inst.id, "definition": inst.definition, "name": DEFINITIONS[inst.definition].name,
        "entity": inst.entity, "entity_id": inst.entity_id, "entity_ref": inst.entity_ref, "title": inst.title,
        "status": inst.status.value, "amount": inst.amount, "started_at": inst.started_at,
        "stage_index": inst.stage_index, "stages": [{"key": s.key, "label": s.label, "permission": s.permission} for s in stages],
        "current_stage": stages[inst.stage_index].label if inst.status == InstanceStatus.active else None,
        "due_at": inst.stage_due_at, "overdue": bool(due and due < now),
        "history": [{"stage": a.stage_key, "action": a.action, "by": a.actor_label, "note": a.note, "at": a.at} for a in inst.actions],
    }
    if p is not None and db is not None:
        out["can_act"], out["why_not"] = can_act(db, p, inst)
    return out
