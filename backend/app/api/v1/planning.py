"""Phase 2 — academic terms, menus, school demand and procurement plans (FR-DEM-01…07, FR-PRO-01)."""
import uuid
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, current_principal, ensure_in_scope, require, scope_for
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import (AcademicTerm, BudgetException, BudgetLine, Commodity, DemandStatus, ExceptionStatus, Menu,
                        MenuDay, MenuStatus, Organization, OrgType, PlanLine, PlanStatus, ProcurementPlan,
                        SchoolDemand)
from app.services import audit, budget, demand as calc, workflow as wf

router = APIRouter(tags=["planning (demand & plans)"])


def county_of(db: Session, org_id) -> uuid.UUID | None:
    o = db.get(Organization, org_id)
    while o is not None and o.type != OrgType.county:
        o = db.get(Organization, o.parent_id) if o.parent_id else None
    return o.id if o else None


def cluster_of(db: Session, org_id) -> Organization | None:
    o = db.get(Organization, org_id)
    while o is not None and o.type != OrgType.school_cluster:
        o = db.get(Organization, o.parent_id) if o.parent_id else None
    return o


# =========================== terms ===========================
class TermIn(BaseModel):
    year: int = Field(ge=2020, le=2100)
    term_no: int = Field(ge=1, le=3)
    name: str
    starts_on: date
    ends_on: date
    feeding_days: int = Field(ge=1, le=120)


class TermOut(TermIn):
    id: uuid.UUID
    is_active: bool
    model_config = {"from_attributes": True}


@router.get("/terms", response_model=list[TermOut])
def terms(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return db.scalars(select(AcademicTerm).order_by(AcademicTerm.year.desc(), AcademicTerm.term_no.desc())).all()


@router.post("/terms", response_model=TermOut, status_code=201)
def create_term(body: TermIn, request: Request, p: Principal = Depends(require("md:create")), db: Session = Depends(get_db)):
    if body.ends_on <= body.starts_on:
        raise AppError(422, "VALIDATION_ERROR", "The term must end after it starts.")
    if db.scalar(select(AcademicTerm).where(AcademicTerm.year == body.year, AcademicTerm.term_no == body.term_no)):
        raise AppError(409, "CONFLICT", "This term already exists.")
    t = AcademicTerm(**body.model_dump(), created_by=p.id)
    db.add(t)
    db.flush()
    audit.record(db, action="CREATE", entity="term", entity_id=t.id, user=p.user, after=body.model_dump(), request=request)
    db.commit()
    return t


# =========================== menus ===========================
class Component(BaseModel):
    commodity: str
    portion_g: Decimal = Field(gt=0, le=1000)


class MenuDayIn(BaseModel):
    label: str = Field(max_length=40)
    dish: str = Field(max_length=200)
    components: list[Component]


class MenuIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    org_id: uuid.UUID | None = None
    days: list[MenuDayIn] = Field(min_length=1, max_length=10)


def _menu_out(db: Session, m: Menu, p: Principal | None = None) -> dict:
    inst = wf.active_for(db, "menu", m.id)
    return {"id": m.id, "name": m.name, "description": m.description, "org_id": m.org_id, "status": m.status.value,
            "approved_at": m.approved_at, "updated_at": m.updated_at,
            "days": [{"label": d.label, "dish": d.dish, "components": d.components} for d in m.days],
            "summary": calc.menu_summary(db, m),
            "workflow": wf.serialize(inst, p, db) if inst else None}


@router.get("/menus")
def menus(status: MenuStatus | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if not (p.can("dem:view") or p.can("md:view")):
        raise AppError(403, "FORBIDDEN", "You do not have permission to view menus.")
    stmt = select(Menu).options(selectinload(Menu.days)).order_by(Menu.name)
    if status:
        stmt = stmt.where(Menu.status == status)
    return [_menu_out(db, m, p) for m in db.scalars(stmt).all()]


def _apply_menu(db: Session, m: Menu, body: MenuIn):
    known = set(db.scalars(select(Commodity.code)).all())
    bad = {c.commodity for d in body.days for c in d.components if c.commodity not in known}
    if bad:
        raise AppError(422, "VALIDATION_ERROR", "Unknown commodity: " + ", ".join(sorted(bad)))
    m.name, m.description, m.org_id = body.name, body.description, body.org_id
    m.days.clear()
    db.flush()
    for i, d in enumerate(body.days, 1):
        m.days.append(MenuDay(day_index=i, label=d.label, dish=d.dish,
                              components=[{"commodity": c.commodity, "portion_g": float(c.portion_g)} for c in d.components]))


@router.post("/menus", status_code=201)
def create_menu(body: MenuIn, request: Request, p: Principal = Depends(require("md:create")), db: Session = Depends(get_db)):
    allowed = scope_for(db, p, "md:create")
    if body.org_id is None and allowed is not None:
        # county-scoped users create county menus; programme-wide templates need a national-scope user
        body.org_id = next(o for o in p.grants["md:create"] if o is not None)
    if body.org_id is not None:
        ensure_in_scope(db, p, "md:create", body.org_id)
    m = Menu(name=body.name, created_by=p.id)
    db.add(m)
    _apply_menu(db, m, body)
    db.flush()
    audit.record(db, action="CREATE", entity="menu", entity_id=m.id, user=p.user, after={"name": m.name}, request=request)
    db.commit()
    return _menu_out(db, m, p)


@router.put("/menus/{mid}")
def update_menu(mid: uuid.UUID, body: MenuIn, request: Request, p: Principal = Depends(require("md:edit")),
                db: Session = Depends(get_db)):
    m = db.get(Menu, mid)
    if m is None:
        raise AppError(404, "NOT_FOUND", "Menu not found.")
    if m.status != MenuStatus.draft:
        raise AppError(409, "LOCKED", "Only draft menus can be edited. Copy the menu to make changes.")
    _apply_menu(db, m, body)
    m.updated_by = p.id
    audit.record(db, action="UPDATE", entity="menu", entity_id=m.id, user=p.user, after={"name": m.name}, request=request)
    db.commit()
    return _menu_out(db, m, p)


@router.post("/menus/{mid}/submit")
def submit_menu(mid: uuid.UUID, request: Request, p: Principal = Depends(require("md:submit")), db: Session = Depends(get_db)):
    m = db.get(Menu, mid)
    if m is None or m.status != MenuStatus.draft:
        raise AppError(409, "INVALID_TRANSITION", "Only draft menus can be submitted.")
    m.status = MenuStatus.submitted
    wf.start(db, "menu", entity="menu", entity_id=m.id, entity_ref=m.name, title=f"Menu: {m.name}",
             scope_org_id=m.org_id, initiator=p)
    audit.record(db, action="SUBMIT", entity="menu", entity_id=m.id, user=p.user, request=request)
    db.commit()
    return _menu_out(db, m, p)


def _menu_done(db, inst, p, note):
    m = db.get(Menu, inst.entity_id)
    m.status, m.approved_by, m.approved_at = MenuStatus.approved, p.id, utcnow()


def _menu_back(db, inst, p, note):
    db.get(Menu, inst.entity_id).status = MenuStatus.draft


wf.DEFINITIONS["menu"].hooks.update(complete=_menu_done, reject=_menu_back, **{"return": _menu_back})


# =========================== school demand ===========================
class StockIn(BaseModel):
    commodity: str
    qty: Decimal = Field(ge=0)


class OverrideIn(BaseModel):
    commodity: str
    qty: Decimal | None = Field(default=None, ge=0)
    reason: str = ""


class DemandIn(BaseModel):
    school_id: uuid.UUID
    term_id: uuid.UUID
    menu_id: uuid.UUID | None = None
    enrolment: int = Field(ge=0, le=20000)
    attendance_pct: Decimal = Field(default=Decimal("95"), gt=0, le=100)
    feeding_days: int = Field(ge=0, le=120)
    wastage_pct: Decimal = Field(default=Decimal("3"), ge=0, le=20)
    storage_capacity_kg: Decimal | None = None
    preferred_delivery: str = ""
    notes: str = ""
    stock: list[StockIn] = Field(default_factory=list)
    overrides: list[OverrideIn] = Field(default_factory=list)


def _previous(db, d: SchoolDemand):
    return db.scalar(select(SchoolDemand).join(AcademicTerm, SchoolDemand.term_id == AcademicTerm.id)
                     .where(SchoolDemand.school_id == d.school_id, SchoolDemand.id != d.id)
                     .order_by(AcademicTerm.year.desc(), AcademicTerm.term_no.desc()))


def _demand_out(db: Session, d: SchoolDemand, p: Principal | None = None, full=True) -> dict:
    comms = {c.code: c for c in db.scalars(select(Commodity)).all()}
    out = {"id": d.id, "reference": d.reference, "school_id": d.school_id, "school": d.school.name if d.school else None,
           "county_id": d.county_id, "term_id": d.term_id, "term": d.term.name if d.term else None, "menu_id": d.menu_id,
           "menu": d.menu.name if d.menu else None, "enrolment": d.enrolment, "attendance_pct": d.attendance_pct,
           "feeding_days": d.feeding_days, "wastage_pct": d.wastage_pct, "storage_capacity_kg": d.storage_capacity_kg,
           "preferred_delivery": d.preferred_delivery, "notes": d.notes, "status": d.status.value, "flags": d.flags,
           "plan_id": d.plan_id, "updated_at": d.updated_at,
           "total_kg": sum((ln.final_qty for ln in d.lines if ln.unit == "kg"), Decimal(0))}
    if full:
        out["nutrition"] = d.nutrition
        out["lines"] = [{"commodity": ln.commodity_code, "name": comms[ln.commodity_code].name if ln.commodity_code in comms else ln.commodity_code,
                         "unit": ln.unit, "grams_per_learner_cycle": ln.grams_per_learner_cycle, "gross_qty": ln.gross_qty,
                         "stock_qty": ln.stock_qty, "net_qty": ln.net_qty, "override_qty": ln.override_qty,
                         "override_reason": ln.override_reason, "final_qty": ln.final_qty} for ln in d.lines]
        inst = wf.active_for(db, "school_demand", d.id)
        out["workflow"] = wf.serialize(inst, p, db) if inst else None
        from app.models import WorkflowInstance
        last = db.scalar(select(WorkflowInstance).where(WorkflowInstance.entity == "school_demand",
                                                        WorkflowInstance.entity_id == d.id)
                         .order_by(WorkflowInstance.started_at.desc()))
        out["history"] = wf.serialize(last)["history"] if last else []
    return out


def _load_demand(db, did) -> SchoolDemand:
    d = db.scalar(select(SchoolDemand).where(SchoolDemand.id == did).options(
        selectinload(SchoolDemand.lines), selectinload(SchoolDemand.school), selectinload(SchoolDemand.term),
        selectinload(SchoolDemand.menu)))
    if d is None:
        raise AppError(404, "NOT_FOUND", "Demand not found.")
    return d


def _apply_demand(db: Session, d: SchoolDemand, body: DemandIn):
    term = db.get(AcademicTerm, body.term_id)
    if term is None:
        raise AppError(422, "VALIDATION_ERROR", "Unknown term.")
    if body.menu_id:
        m = db.get(Menu, body.menu_id)
        if m is None or m.status != MenuStatus.approved:
            raise AppError(422, "VALIDATION_ERROR", "Choose an approved menu.")
    for k in ("menu_id", "enrolment", "attendance_pct", "feeding_days", "wastage_pct", "storage_capacity_kg",
              "preferred_delivery", "notes"):
        setattr(d, k, getattr(body, k))
    d.term = term
    calc.calculate(db, d, {s.commodity: s.qty for s in body.stock})
    ov = {o.commodity: o for o in body.overrides}
    for ln in d.lines:
        if ln.commodity_code in ov:
            ln.override_qty, ln.override_reason = ov[ln.commodity_code].qty, ov[ln.commodity_code].reason
    d.flags = calc.validate(db, d, _previous(db, d))


@router.get("/demands")
def list_demands(term_id: uuid.UUID | None = None, status: DemandStatus | None = None, school_id: uuid.UUID | None = None,
                 p: Principal = Depends(require("dem:view")), db: Session = Depends(get_db)):
    stmt = select(SchoolDemand).options(selectinload(SchoolDemand.lines), selectinload(SchoolDemand.school),
                                        selectinload(SchoolDemand.term), selectinload(SchoolDemand.menu))
    allowed = scope_for(db, p, "dem:view")
    if allowed is not None:
        stmt = stmt.where(SchoolDemand.school_id.in_(allowed))
    if term_id:
        stmt = stmt.where(SchoolDemand.term_id == term_id)
    if status:
        stmt = stmt.where(SchoolDemand.status == status)
    if school_id:
        stmt = stmt.where(SchoolDemand.school_id == school_id)
    return [_demand_out(db, d, full=False) for d in db.scalars(stmt.order_by(SchoolDemand.updated_at.desc())).all()]


@router.get("/demands/schools")
def my_schools(p: Principal = Depends(require("dem:view")), db: Session = Depends(get_db)):
    """Schools the user can plan for (for the school picker)."""
    stmt = select(Organization).where(Organization.type == OrgType.school, Organization.is_active)
    allowed = scope_for(db, p, "dem:view")
    if allowed is not None:
        stmt = stmt.where(Organization.id.in_(allowed))
    return [{"id": o.id, "name": o.name, "code": o.code, "meta": o.meta} for o in db.scalars(stmt.order_by(Organization.name))]


@router.post("/demands", status_code=201)
def create_demand(body: DemandIn, request: Request, p: Principal = Depends(require("dem:create")), db: Session = Depends(get_db)):
    school = db.get(Organization, body.school_id)
    if school is None or school.type != OrgType.school:
        raise AppError(422, "VALIDATION_ERROR", "Choose a school.")
    ensure_in_scope(db, p, "dem:create", school.id)
    if db.scalar(select(SchoolDemand).where(SchoolDemand.school_id == school.id, SchoolDemand.term_id == body.term_id)):
        raise AppError(409, "CONFLICT", "A demand plan already exists for this school and term.")
    term = db.get(AcademicTerm, body.term_id)
    d = SchoolDemand(reference=f"DEM-{school.code}-{term.year}T{term.term_no}" if term else f"DEM-{uuid.uuid4().hex[:8]}",
                     school_id=school.id, county_id=county_of(db, school.id), term_id=body.term_id, created_by=p.id)
    db.add(d)
    db.flush()
    _apply_demand(db, d, body)
    audit.record(db, action="CREATE", entity="school_demand", entity_id=d.id, user=p.user,
                 after={"reference": d.reference, "enrolment": d.enrolment}, request=request)
    db.commit()
    return _demand_out(db, _load_demand(db, d.id), p)


@router.get("/demands/{did}")
def get_demand(did: uuid.UUID, p: Principal = Depends(require("dem:view")), db: Session = Depends(get_db)):
    d = _load_demand(db, did)
    ensure_in_scope(db, p, "dem:view", d.school_id)
    return _demand_out(db, d, p)


@router.put("/demands/{did}")
def update_demand(did: uuid.UUID, body: DemandIn, request: Request, p: Principal = Depends(require("dem:edit")),
                  db: Session = Depends(get_db)):
    d = _load_demand(db, did)
    ensure_in_scope(db, p, "dem:edit", d.school_id)
    if d.status not in (DemandStatus.draft, DemandStatus.returned):
        raise AppError(409, "LOCKED", "This demand is in approval or already approved and cannot be edited.")
    before = {"enrolment": d.enrolment, "feeding_days": d.feeding_days, "menu_id": d.menu_id}
    _apply_demand(db, d, body)
    d.updated_by = p.id
    audit.record(db, action="UPDATE", entity="school_demand", entity_id=d.id, user=p.user, before=before,
                 after={"enrolment": d.enrolment, "feeding_days": d.feeding_days, "menu_id": d.menu_id}, request=request)
    db.commit()
    return _demand_out(db, _load_demand(db, d.id), p)


@router.post("/demands/{did}/submit")
def submit_demand(did: uuid.UUID, request: Request, p: Principal = Depends(require("dem:submit")), db: Session = Depends(get_db)):
    d = _load_demand(db, did)
    ensure_in_scope(db, p, "dem:submit", d.school_id)
    if d.status not in (DemandStatus.draft, DemandStatus.returned):
        raise AppError(409, "INVALID_TRANSITION", "Only draft or returned demands can be submitted.")
    d.flags = calc.validate(db, d, _previous(db, d))
    errors = [f["message"] for f in d.flags if f["severity"] == "error"]
    if errors:
        db.commit()
        raise AppError(422, "DEMAND_INVALID", "Fix these before submitting: " + " ".join(errors))
    d.status = DemandStatus.submitted
    wf.start(db, "school_demand", entity="school_demand", entity_id=d.id, entity_ref=d.reference,
             title=f"{d.school.name} · {d.term.name}", scope_org_id=d.school_id, initiator=p)
    audit.record(db, action="SUBMIT", entity="school_demand", entity_id=d.id, user=p.user, request=request)
    db.commit()
    return _demand_out(db, d, p)


def _dem_advance(db, inst, p, note):
    db.get(SchoolDemand, inst.entity_id).status = DemandStatus.validated


def _dem_done(db, inst, p, note):
    db.get(SchoolDemand, inst.entity_id).status = DemandStatus.approved


def _dem_back(db, inst, p, note):
    db.get(SchoolDemand, inst.entity_id).status = DemandStatus.returned


wf.DEFINITIONS["school_demand"].hooks.update(advance=_dem_advance, complete=_dem_done, reject=_dem_back,
                                             **{"return": _dem_back})


# =========================== procurement plans ===========================
class ConsolidateIn(BaseModel):
    county_id: uuid.UUID
    term_id: uuid.UUID
    group_by: str = Field(default="cluster", pattern="^(cluster|county)$")


class PlanLineIn(BaseModel):
    id: uuid.UUID
    unit_price: Decimal | None = Field(default=None, ge=0)
    delivery_window: str = ""


class PlanUpdateIn(BaseModel):
    title: str | None = None
    budget_line_id: uuid.UUID | None = None
    method: str | None = Field(default=None, pattern="^(rfq|competitive|framework|call_off|direct)$")
    notes: str | None = None
    lines: list[PlanLineIn] = Field(default_factory=list)


def _consolidate(db: Session, county_id, term_id, group_by: str):
    demands = db.scalars(select(SchoolDemand).options(selectinload(SchoolDemand.lines), selectinload(SchoolDemand.school))
                         .where(SchoolDemand.county_id == county_id, SchoolDemand.term_id == term_id,
                                SchoolDemand.status == DemandStatus.approved, SchoolDemand.plan_id.is_(None))).all()
    comms = {c.code: c for c in db.scalars(select(Commodity)).all()}
    buckets: dict[tuple, dict] = defaultdict(lambda: {"quantity": Decimal(0), "schools": []})
    for d in demands:
        cl = cluster_of(db, d.school_id) if group_by == "cluster" else None
        for ln in d.lines:
            if ln.final_qty <= 0:
                continue
            c = comms.get(ln.commodity_code)
            cat = c.category if c else "other"
            key = (cl.id if cl else None, cl.name if cl else "All schools", cat, ln.commodity_code)
            b = buckets[key]
            b["quantity"] += ln.final_qty
            b["unit"] = ln.unit
            b["schools"].append({"school_id": str(d.school_id), "name": d.school.name, "qty": str(ln.final_qty)})
    lines = []
    for (cl_id, cl_name, cat, code), b in sorted(buckets.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][3])):
        c = comms.get(code)
        lines.append({"lot": f"{cl_name} · {cat.replace('_', ' ')}", "cluster_id": cl_id, "commodity_code": code,
                      "name": c.name if c else code, "unit": b["unit"], "quantity": b["quantity"],
                      "unit_price": c.reference_price if c else None, "schools": b["schools"]})
    return demands, lines


def _plan_out(db: Session, pl: ProcurementPlan, p: Principal | None = None) -> dict:
    comms = {c.code: c for c in db.scalars(select(Commodity)).all()}
    est = pl.estimated_value
    out = {"id": pl.id, "reference": pl.reference, "title": pl.title, "county_id": pl.county_id,
           "county": pl.county.name if pl.county else None, "term_id": pl.term_id, "term": pl.term.name if pl.term else None,
           "budget_line_id": pl.budget_line_id, "method": pl.method, "status": pl.status.value, "notes": pl.notes,
           "estimated_value": est, "unpriced_lines": sum(1 for ln in pl.lines if ln.unit_price is None),
           "updated_at": pl.updated_at,
           "lines": [{"id": ln.id, "lot": ln.lot, "commodity_code": ln.commodity_code,
                      "name": comms[ln.commodity_code].name if ln.commodity_code in comms else ln.commodity_code,
                      "unit": ln.unit, "quantity": ln.quantity, "unit_price": ln.unit_price,
                      "estimated_value": ln.estimated_value, "schools": ln.schools, "delivery_window": ln.delivery_window}
                     for ln in pl.lines]}
    out["demand_count"] = db.scalar(select(func.count()).select_from(SchoolDemand).where(SchoolDemand.plan_id == pl.id))
    if pl.budget_line_id:
        bl = db.get(BudgetLine, pl.budget_line_id)
        out["budget"] = {"line": bl.name, **{k: v for k, v in budget.check(db, bl, est).items()}}
        exc = db.scalar(select(BudgetException).where(BudgetException.source_entity == "procurement_plan",
                                                      BudgetException.source_id == pl.id)
                        .order_by(BudgetException.created_at.desc()))
        out["exception"] = ({"id": exc.id, "status": exc.status.value, "shortfall": exc.shortfall,
                             "justification": exc.justification, "decision_note": exc.decision_note} if exc else None)
    inst = wf.active_for(db, "procurement_plan", pl.id)
    out["workflow"] = wf.serialize(inst, p, db) if inst else None
    from app.models import WorkflowInstance
    last = db.scalar(select(WorkflowInstance).where(WorkflowInstance.entity == "procurement_plan",
                                                    WorkflowInstance.entity_id == pl.id)
                     .order_by(WorkflowInstance.started_at.desc()))
    out["history"] = wf.serialize(last)["history"] if last else []
    return out


def _load_plan(db, pid) -> ProcurementPlan:
    pl = db.scalar(select(ProcurementPlan).where(ProcurementPlan.id == pid).options(
        selectinload(ProcurementPlan.lines), selectinload(ProcurementPlan.county), selectinload(ProcurementPlan.term)))
    if pl is None:
        raise AppError(404, "NOT_FOUND", "Plan not found.")
    return pl


@router.post("/plans/preview")
def preview_plan(body: ConsolidateIn, p: Principal = Depends(require("src:create")), db: Session = Depends(get_db)):
    ensure_in_scope(db, p, "src:create", body.county_id)
    demands, lines = _consolidate(db, body.county_id, body.term_id, body.group_by)
    return {"demand_count": len(demands), "schools": [d.school.name for d in demands], "lines": lines}


@router.post("/plans", status_code=201)
def create_plan(body: ConsolidateIn, request: Request, p: Principal = Depends(require("src:create")), db: Session = Depends(get_db)):
    """FR-DEM-04/07: consolidate approved school demand into a procurement plan (lots by cluster × category)."""
    ensure_in_scope(db, p, "src:create", body.county_id)
    demands, lines = _consolidate(db, body.county_id, body.term_id, body.group_by)
    if not demands:
        raise AppError(409, "NOTHING_TO_PLAN", "There is no approved school demand for this county and term.")
    county, term = db.get(Organization, body.county_id), db.get(AcademicTerm, body.term_id)
    seq = (db.scalar(select(func.count()).select_from(ProcurementPlan).where(ProcurementPlan.county_id == county.id)) or 0) + 1
    pl = ProcurementPlan(reference=f"PLAN-{county.code}-{term.year}T{term.term_no}-{seq:02d}",
                         title=f"{county.name} · {term.name} school food procurement", county_id=county.id,
                         term_id=term.id, created_by=p.id)
    db.add(pl)
    db.flush()
    for ln in lines:
        pl.lines.append(PlanLine(lot=ln["lot"], cluster_id=ln["cluster_id"], commodity_code=ln["commodity_code"],
                                 unit=ln["unit"], quantity=ln["quantity"], unit_price=ln["unit_price"], schools=ln["schools"]))
    for d in demands:
        d.plan_id, d.status = pl.id, DemandStatus.converted
    audit.record(db, action="CREATE", entity="procurement_plan", entity_id=pl.id, user=p.user,
                 after={"reference": pl.reference, "demands": len(demands), "lines": len(lines)}, request=request)
    db.commit()
    return _plan_out(db, _load_plan(db, pl.id), p)


@router.get("/plans")
def list_plans(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if not (p.can("src:view") or p.can("bud:view") or p.can("dem:approve")):
        raise AppError(403, "FORBIDDEN", "You do not have permission to view procurement plans.")
    code = next(c for c in ("src:view", "bud:view", "dem:approve") if p.can(c))
    stmt = select(ProcurementPlan).options(selectinload(ProcurementPlan.lines), selectinload(ProcurementPlan.county),
                                           selectinload(ProcurementPlan.term))
    allowed = scope_for(db, p, code)
    if allowed is not None:
        stmt = stmt.where(ProcurementPlan.county_id.in_(allowed))
    return [{k: v for k, v in _plan_out(db, pl).items() if k != "lines"}
            for pl in db.scalars(stmt.order_by(ProcurementPlan.updated_at.desc())).all()]


@router.get("/plans/{pid}")
def get_plan(pid: uuid.UUID, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    pl = _load_plan(db, pid)
    if not any(p.can(c) for c in ("src:view", "bud:view", "dem:approve")):
        raise AppError(403, "FORBIDDEN", "You do not have permission to view procurement plans.")
    code = next(c for c in ("src:view", "bud:view", "dem:approve") if p.can(c))
    ensure_in_scope(db, p, code, pl.county_id)
    return _plan_out(db, pl, p)


@router.put("/plans/{pid}")
def update_plan(pid: uuid.UUID, body: PlanUpdateIn, request: Request, p: Principal = Depends(require("src:edit")),
                db: Session = Depends(get_db)):
    pl = _load_plan(db, pid)
    ensure_in_scope(db, p, "src:edit", pl.county_id)
    if pl.status not in (PlanStatus.draft, PlanStatus.returned):
        raise AppError(409, "LOCKED", "This plan is in approval or already approved.")
    if body.budget_line_id:
        bl = db.get(BudgetLine, body.budget_line_id)
        if bl is None or not bl.is_active:
            raise AppError(422, "VALIDATION_ERROR", "Unknown budget line.")
    for k in ("title", "budget_line_id", "method", "notes"):
        v = getattr(body, k)
        if v is not None:
            setattr(pl, k, v)
    idx = {ln.id: ln for ln in pl.lines}
    for li in body.lines:
        if li.id in idx:
            idx[li.id].unit_price, idx[li.id].delivery_window = li.unit_price, li.delivery_window
    pl.updated_by = p.id
    audit.record(db, action="UPDATE", entity="procurement_plan", entity_id=pl.id, user=p.user,
                 after={"budget_line_id": pl.budget_line_id, "estimated_value": pl.estimated_value}, request=request)
    db.commit()
    return _plan_out(db, _load_plan(db, pl.id), p)


def _approved_exception(db, pl) -> BudgetException | None:
    return db.scalar(select(BudgetException).where(BudgetException.source_entity == "procurement_plan",
                                                   BudgetException.source_id == pl.id,
                                                   BudgetException.status == ExceptionStatus.approved))


@router.post("/plans/{pid}/submit")
def submit_plan(pid: uuid.UUID, request: Request, p: Principal = Depends(require("src:submit")), db: Session = Depends(get_db)):
    pl = _load_plan(db, pid)
    ensure_in_scope(db, p, "src:submit", pl.county_id)
    if pl.status not in (PlanStatus.draft, PlanStatus.returned):
        raise AppError(409, "INVALID_TRANSITION", "Only draft or returned plans can be submitted.")
    if not pl.budget_line_id:
        raise AppError(422, "NO_BUDGET", "Choose the budget line that will fund this plan (FR-BUD-03).")
    if any(ln.unit_price is None for ln in pl.lines):
        raise AppError(422, "UNPRICED", "Enter an estimated unit price for every line.")
    chk = budget.check(db, db.get(BudgetLine, pl.budget_line_id), pl.estimated_value)
    if not chk["sufficient"] and _approved_exception(db, pl) is None:
        raise AppError(409, "BUDGET_EXCEEDED",
                       f"Available budget KSh {chk['available']:,.2f} is less than the plan estimate KSh {pl.estimated_value:,.2f}. "
                       "Reduce the plan or request a budget exception.",
                       [{"available": str(chk["available"]), "shortfall": str(chk["shortfall"])}])
    pl.status = PlanStatus.submitted
    wf.start(db, "procurement_plan", entity="procurement_plan", entity_id=pl.id, entity_ref=pl.reference,
             title=pl.title, scope_org_id=pl.county_id, initiator=p, amount=float(pl.estimated_value))
    audit.record(db, action="SUBMIT", entity="procurement_plan", entity_id=pl.id, user=p.user,
                 after={"estimated_value": pl.estimated_value}, request=request)
    db.commit()
    return _plan_out(db, pl, p)


def _plan_budget_ok(db, inst, p, note):
    """Stage 1 approve (finance): re-check budget at the moment of confirmation."""
    pl = _load_plan(db, inst.entity_id)
    chk = budget.check(db, db.get(BudgetLine, pl.budget_line_id), pl.estimated_value)
    if not chk["sufficient"] and _approved_exception(db, pl) is None:
        raise AppError(409, "BUDGET_EXCEEDED", "Budget is no longer sufficient. Return the plan or approve an exception.")


def _plan_done(db, inst, p, note):
    pl = _load_plan(db, inst.entity_id)
    exc = _approved_exception(db, pl)
    budget.commit(db, db.get(BudgetLine, pl.budget_line_id), amount=pl.estimated_value, source_entity="procurement_plan",
                  source_id=pl.id, source_ref=pl.reference, exception_id=exc.id if exc else None, actor_id=p.id)
    pl.status = PlanStatus.approved


def _plan_back(db, inst, p, note):
    pl = db.get(ProcurementPlan, inst.entity_id)
    pl.status = PlanStatus.returned


def _plan_rejected(db, inst, p, note):
    pl = db.get(ProcurementPlan, inst.entity_id)
    pl.status = PlanStatus.rejected
    for d in db.scalars(select(SchoolDemand).where(SchoolDemand.plan_id == pl.id)):
        d.plan_id, d.status = None, DemandStatus.approved     # demand becomes available for a new plan


wf.DEFINITIONS["procurement_plan"].hooks.update(advance=_plan_budget_ok, complete=_plan_done, reject=_plan_rejected,
                                                **{"return": _plan_back})
