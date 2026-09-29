"""Complaints & grievances (SRS §3.12, FR-CMP-01…04): raised by schools, suppliers, staff or the public,
routed to the county with a service-level due date, investigated, resolved and confirmed by the complainant."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require, scope_for
from app.core.errors import AppError
from app.core.timeutil import as_utc, utcnow
from app.models import Complaint, ComplaintStatus, Organization, OrgType, Supplier, User
from app.services import audit, notifications as note, stock
from app.services.refs import next_ref

router = APIRouter(prefix="/complaints", tags=["complaints"])
CATEGORIES = {"food_quality": "Food quality", "late_delivery": "Late delivery", "short_delivery": "Short or missing delivery",
              "supplier_conduct": "Supplier conduct", "staff_conduct": "Staff conduct", "payment": "Payment delay or error",
              "procurement": "Procurement fairness", "safeguarding": "Safeguarding", "fraud": "Suspected fraud or corruption", "other": "Other"}
SLA_DAYS = {"high": 3, "medium": 7, "low": 14}
SENSITIVE = {"safeguarding", "fraud", "staff_conduct"}      # always high priority


def _supplier_of(db, p: Principal) -> Supplier | None:
    orgs = {ur.org_id for ur in p.user.roles if ur.is_active and ur.org_id}
    return db.scalar(select(Supplier).where(Supplier.organization_id.in_(orgs))) if orgs else None


def complaint_out(db, c: Complaint, p: Principal | None = None) -> dict:
    school = db.get(Organization, c.school_id) if c.school_id else None
    county = db.get(Organization, c.org_id) if c.org_id else None
    sup = db.get(Supplier, c.supplier_id) if c.supplier_id else None
    by = db.get(User, c.submitted_by) if c.submitted_by else None
    ass = db.get(User, c.assigned_to) if c.assigned_to else None
    due = as_utc(c.due_at)
    open_ = c.status in (ComplaintStatus.submitted, ComplaintStatus.investigating)
    internal = p is not None and (p.can("cmp:approve") or (p.can("cmp:create") and _supplier_of(db, p) is None and not _is_school_only(p)))
    show_contact = not c.anonymous and (internal or (p is not None and c.submitted_by == p.id))
    out = {"id": c.id, "reference": c.reference, "channel": c.channel, "category": c.category, "category_label": CATEGORIES.get(c.category, c.category),
           "priority": c.priority, "subject": c.subject, "description": c.description, "county": county.name if county else None,
           "school": school.name if school else None, "supplier": sup.legal_name if sup else None, "supplier_id": c.supplier_id,
           "entity": c.entity, "entity_id": c.entity_id, "entity_ref": c.entity_ref,
           "submitted_by": ("Anonymous" if c.anonymous else (by.full_name if by else c.contact_name or "Member of the public")),
           "contact": c.contact if show_contact else "", "status": c.status.value, "assigned_to": ass.full_name if ass else None,
           "due_at": c.due_at, "overdue": bool(open_ and due and due < utcnow()), "resolution": c.resolution, "resolved_at": c.resolved_at,
           "satisfaction": c.satisfaction, "history": c.history, "created_at": c.created_at}
    if p is not None:
        out["actions"] = _allowed_actions(db, p, c)
    return out


def _is_school_only(p: Principal) -> bool:
    return bool(p.role_keys) and p.role_keys <= {"school_admin", "school_meals_officer"}


def _in_scope(db, p, code, c: Complaint) -> bool:
    if not p.can(code):
        return False
    allowed = scope_for(db, p, code)
    return allowed is None or (c.org_id in allowed if c.org_id else False) or (c.school_id in allowed if c.school_id else False)


def _allowed_actions(db, p: Principal, c: Complaint) -> list[str]:
    acts = ["comment"]
    mine = c.submitted_by == p.id
    handler = not mine and (_in_scope(db, p, "cmp:approve", c) or (_in_scope(db, p, "cmp:create", c) and _supplier_of(db, p) is None
                                                                    and not _is_school_only(p)))
    if c.status in (ComplaintStatus.submitted, ComplaintStatus.investigating):
        if handler:
            acts.append("investigate")
        if not mine and _in_scope(db, p, "cmp:approve", c):
            acts.append("resolve")
        sup = _supplier_of(db, p)
        if sup and c.supplier_id == sup.id:
            acts.append("respond")
    if c.status == ComplaintStatus.resolved and mine:
        acts += ["confirm", "reopen"]
    return acts


def _can_see(db, p: Principal, c: Complaint) -> bool:
    allowed = scope_for(db, p, "cmp:view")
    if allowed is None or c.submitted_by == p.id:
        return True
    sup = _supplier_of(db, p)
    if sup:   # suppliers see complaints about them so they can respond, except sensitive ones (whistle-blower protection)
        return c.supplier_id == sup.id and c.category not in SENSITIVE
    if _is_school_only(p):
        return c.school_id in allowed
    return c.org_id in allowed or c.school_id in allowed


def _log(c: Complaint, p: Principal | None, action: str, note_: str = ""):
    c.history = [*(c.history or []), {"at": utcnow().isoformat(), "by": p.user.full_name if p else "system", "action": action, "note": note_}]


def create_complaint(db: Session, *, category: str, subject: str, description: str, priority: str = "medium", channel="portal",
                     org_id=None, school_id=None, supplier_id=None, entity="", entity_id=None, entity_ref="", submitted_by=None,
                     contact_name="", contact="", anonymous=False, actor: Principal | None = None) -> Complaint:
    if category not in CATEGORIES:
        raise AppError(422, "VALIDATION_ERROR", "Choose a category.", [{"field": "category", "message": "Unknown category"}])
    if category in SENSITIVE:
        priority = "high"
    c = Complaint(reference=next_ref(db, Complaint, "CMP"), channel=channel, category=category, priority=priority,
                  subject=subject.strip()[:200], description=description.strip(), org_id=org_id, school_id=school_id, supplier_id=supplier_id,
                  entity=entity, entity_id=entity_id, entity_ref=entity_ref, submitted_by=submitted_by, contact_name=contact_name.strip(),
                  contact=contact.strip(), anonymous=anonymous, due_at=utcnow() + timedelta(days=SLA_DAYS.get(priority, 7)),
                  history=[], created_by=submitted_by)
    _log(c, actor, "submitted", f"via {channel}")
    db.add(c)
    db.flush()
    handlers = []
    if org_id:
        handlers = note.users_with_role(db, "county_procurement_officer", org_id) + note.users_with_role(db, "county_admin", org_id)
        if category in SENSITIVE:
            handlers += note.users_with_role(db, "risk_compliance_officer", org_id)
    note.to_users(db, handlers, f"New complaint {c.reference}: {CATEGORIES[category]}", c.subject, f"/app/complaints?id={c.id}", "complaint")
    return c


class ComplaintIn(BaseModel):
    category: str
    subject: str = Field(min_length=4, max_length=200)
    description: str = Field(min_length=10, max_length=5000)
    priority: str = Field(default="medium", pattern="^(high|medium|low)$")
    school_id: uuid.UUID | None = None
    supplier_id: uuid.UUID | None = None
    entity: str = ""
    entity_id: uuid.UUID | None = None
    entity_ref: str = ""
    anonymous: bool = False


@router.get("/categories")
def categories():
    return [{"key": k, "label": v} for k, v in CATEGORIES.items()]


@router.get("/suppliers")
def complainable_suppliers(p: Principal = Depends(require("cmp:create")), db: Session = Depends(get_db)):
    """Suppliers a complaint can be about: those active in the user's county (names only)."""
    allowed = scope_for(db, p, "cmp:create")
    q = select(Supplier).order_by(Supplier.legal_name)
    if allowed is not None:
        counties = {c for c in (stock.county_of(db, o) for o in allowed) if c}
        q = q.where(Supplier.county_id.in_(counties or {uuid.uuid4()}))
    return [{"id": s.id, "name": s.legal_name} for s in db.scalars(q).all()]


@router.post("", status_code=201)
def submit(body: ComplaintIn, request: Request, p: Principal = Depends(require("cmp:create")), db: Session = Depends(get_db)):
    school_id = body.school_id
    if school_id is None:   # school users complain for their own school by default
        own = [ur.org_id for ur in p.user.roles if ur.is_active and ur.org_id and ur.role.key in ("school_admin", "school_meals_officer")]
        school_id = own[0] if own else None
    if school_id:
        s = db.get(Organization, school_id)
        if s is None or s.type != OrgType.school:
            raise AppError(422, "VALIDATION_ERROR", "Unknown school.")
    if body.supplier_id and db.get(Supplier, body.supplier_id) is None:
        raise AppError(422, "VALIDATION_ERROR", "Unknown supplier.")
    base = school_id or next((ur.org_id for ur in p.user.roles if ur.is_active and ur.org_id), None)
    county = stock.county_of(db, base) if base else None
    if county is None:
        sup = _supplier_of(db, p)
        county = sup.county_id if sup else None
    c = create_complaint(db, category=body.category, subject=body.subject, description=body.description, priority=body.priority,
                         org_id=county, school_id=school_id, supplier_id=body.supplier_id, entity=body.entity, entity_id=body.entity_id,
                         entity_ref=body.entity_ref, submitted_by=p.id, anonymous=body.anonymous, actor=p)
    audit.record(db, action="COMPLAINT", entity="complaint", entity_id=c.id, user=p.user, after={"category": c.category, "priority": c.priority},
                 request=request)
    db.commit()
    return complaint_out(db, c, p)


@router.get("")
def list_complaints(status: str | None = None, p: Principal = Depends(require("cmp:view")), db: Session = Depends(get_db)):
    q = select(Complaint)
    allowed = scope_for(db, p, "cmp:view")
    sup = _supplier_of(db, p)
    if allowed is not None:
        conds = [Complaint.submitted_by == p.id]
        if sup:
            conds.append((Complaint.supplier_id == sup.id) & Complaint.category.notin_(SENSITIVE))
        elif _is_school_only(p):
            conds.append(Complaint.school_id.in_(allowed))
        else:
            conds += [Complaint.org_id.in_(allowed), Complaint.school_id.in_(allowed)]
        q = q.where(or_(*conds))
    if status:
        q = q.where(Complaint.status.in_([ComplaintStatus(s) for s in status.split(",")]))
    return [complaint_out(db, c, p) for c in db.scalars(q.order_by(Complaint.created_at.desc()).limit(300)).all()]


class ActionIn(BaseModel):
    action: str
    note: str = ""
    satisfaction: int | None = Field(default=None, ge=1, le=5)


@router.post("/{cid}/actions")
def act(cid: uuid.UUID, body: ActionIn, request: Request, p: Principal = Depends(require("cmp:view")), db: Session = Depends(get_db)):
    c = db.get(Complaint, cid)
    if c is None:
        raise AppError(404, "NOT_FOUND", "Complaint not found.")
    if not _can_see(db, p, c):
        raise AppError(403, "OUT_OF_SCOPE", "This complaint is outside your assigned area.")
    allowed = _allowed_actions(db, p, c)
    if body.action not in allowed:
        raise AppError(403, "FORBIDDEN", "You cannot do that on this complaint." + (
            " The person who raised a complaint cannot investigate or resolve it." if c.submitted_by == p.id else ""))
    if body.action in ("comment", "investigate", "respond", "resolve", "reopen") and len(body.note.strip()) < 3:
        raise AppError(422, "VALIDATION_ERROR", "Please add a note.", [{"field": "note", "message": "Required"}])
    if body.action == "investigate":
        c.status, c.assigned_to = ComplaintStatus.investigating, c.assigned_to or p.id
    elif body.action == "resolve":
        c.status, c.resolution, c.resolved_at = ComplaintStatus.resolved, body.note.strip(), utcnow()
        if c.submitted_by:
            note.to_users(db, [c.submitted_by], f"Complaint {c.reference} resolved", body.note[:200], f"/app/complaints?id={c.id}", "complaint", sms=True)
    elif body.action == "confirm":
        c.status, c.satisfaction = ComplaintStatus.closed, body.satisfaction
    elif body.action == "reopen":
        c.status, c.resolved_at = ComplaintStatus.investigating, None
        c.due_at = utcnow() + timedelta(days=SLA_DAYS.get(c.priority, 7))
    elif body.action == "respond" and c.org_id:
        note.to_users(db, note.users_with_role(db, "county_procurement_officer", c.org_id), f"Supplier responded on {c.reference}",
                      body.note[:200], f"/app/complaints?id={c.id}", "complaint")
    _log(c, p, body.action, body.note.strip() + (f" (satisfaction {body.satisfaction}/5)" if body.satisfaction else ""))
    audit.record(db, action=f"COMPLAINT_{body.action.upper()}", entity="complaint", entity_id=c.id, user=p.user,
                 after={"status": c.status.value}, reason=body.note, request=request)
    db.commit()
    return complaint_out(db, c, p)
