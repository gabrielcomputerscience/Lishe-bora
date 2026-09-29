"""Supplier registry & prequalification (FR-SUP-01…09)."""
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, current_principal, ensure_in_scope, require, scope_for
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import (DocumentStatus, Organization, Supplier, SupplierDocument, SupplierStatus, SupplierType,
                        UserRole)
from app.models.supplier import SUPPLIER_TRANSITIONS
from app.schemas.common import ORM, Msg
from app.services import audit, storage

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

DOC_TYPES = {"registration": "Registration certificate / ID", "kra_pin": "KRA PIN certificate",
             "food_safety": "Food-safety / public-health certificate", "member_list": "Member list",
             "bank": "Bank or M-Pesa details", "tax_compliance": "Tax compliance certificate",
             "licence": "Business licence", "other": "Other"}
REQUIRED_DOCS = {"registration", "bank"}


class DocOut(ORM):
    id: uuid.UUID
    doc_type: str
    version: int
    file_name: str
    content_type: str
    size_bytes: int
    issued_on: date | None
    expires_on: date | None
    status: str
    review_note: str
    created_at: datetime


class SupplierOut(ORM):
    id: uuid.UUID
    organization_id: uuid.UUID
    county_id: uuid.UUID | None
    county_name: str | None = None
    supplier_type: str
    legal_name: str
    registration_no: str
    phone: str
    email: str
    sub_county: str
    commodities: list
    approved_categories: list
    members_count: int | None
    inclusion_claim: dict
    inclusion_consent: bool
    inclusion_verified: bool
    status: str
    status_note: str
    prequalified_until: date | None
    created_at: datetime
    documents: list[DocOut] = []


class ReviewIn(BaseModel):
    to_status: SupplierStatus
    note: str = ""
    approved_categories: list[str] | None = None
    prequalified_until: date | None = None


class InclusionVerifyIn(BaseModel):
    verified: bool
    note: str = ""


class DocReviewIn(BaseModel):
    status: DocumentStatus
    note: str = ""


# which permission each target status needs (SoD: reviewers verify; approvals need 'approve')
NEEDS = {SupplierStatus.under_review: "sup:verify", SupplierStatus.submitted: "sup:verify",
         SupplierStatus.approved: "sup:approve", SupplierStatus.prequalified: "sup:approve",
         SupplierStatus.active: "sup:approve", SupplierStatus.rejected: "sup:reject",
         SupplierStatus.suspended: "sup:approve", SupplierStatus.expired: "sup:approve"}


def _out(s: Supplier) -> SupplierOut:
    o = SupplierOut.model_validate(s)
    o.county_name = s.county.name if s.county else None
    o.documents = [DocOut.model_validate(d) for d in sorted(s.documents, key=lambda d: (d.doc_type, -d.version))]
    return o


def _own_supplier_ids(p: Principal) -> set[uuid.UUID]:
    return {ur.org_id for ur in p.user.roles if ur.is_active and ur.org_id}


def _load(db: Session, sid: uuid.UUID) -> Supplier:
    s = db.scalar(select(Supplier).where(Supplier.id == sid).options(selectinload(Supplier.documents),
                                                                      selectinload(Supplier.county)))
    if s is None:
        raise AppError(404, "NOT_FOUND", "Supplier not found.")
    return s


def _can_see(db: Session, p: Principal, s: Supplier):
    if s.organization_id in _own_supplier_ids(p):
        return
    ensure_in_scope(db, p, "sup:view", s.county_id, s.organization_id)


@router.get("/doc-types")
def doc_types():
    return [{"key": k, "label": v, "required": k in REQUIRED_DOCS} for k, v in DOC_TYPES.items()]


@router.get("")
def list_suppliers(q: str = "", status: SupplierStatus | None = None, type: SupplierType | None = None,
                   county_id: uuid.UUID | None = None, page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100),
                   p: Principal = Depends(require("sup:view")), db: Session = Depends(get_db)):
    stmt = select(Supplier).options(selectinload(Supplier.county), selectinload(Supplier.documents))
    allowed = scope_for(db, p, "sup:view")
    if allowed is not None:
        stmt = stmt.where(or_(Supplier.county_id.in_(allowed), Supplier.organization_id.in_(allowed)))
    if q:
        stmt = stmt.where(or_(func.lower(Supplier.legal_name).like(f"%{q.lower()}%"), Supplier.phone.like(f"%{q}%")))
    if status:
        stmt = stmt.where(Supplier.status == status)
    if type:
        stmt = stmt.where(Supplier.supplier_type == type)
    if county_id:
        stmt = stmt.where(Supplier.county_id == county_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Supplier.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    counts = dict(db.execute(select(Supplier.status, func.count()).group_by(Supplier.status)).all()) if allowed is None else {}
    return {"total": total, "items": [_out(s) for s in rows],
            "counts": {k.value if hasattr(k, "value") else k: v for k, v in counts.items()}}


@router.get("/me", response_model=SupplierOut)
def my_supplier(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    ids = _own_supplier_ids(p)
    s = db.scalar(select(Supplier).where(Supplier.organization_id.in_(ids)).options(
        selectinload(Supplier.documents), selectinload(Supplier.county))) if ids else None
    if s is None:
        raise AppError(404, "NOT_FOUND", "No supplier profile is linked to your account.")
    return _out(s)


@router.get("/{sid}", response_model=SupplierOut)
def get_supplier(sid: uuid.UUID, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = _load(db, sid)
    _can_see(db, p, s)
    return _out(s)


@router.post("/{sid}/documents", response_model=DocOut, status_code=201)
async def upload_document(sid: uuid.UUID, request: Request, doc_type: str = Form(...), file: UploadFile = File(...),
                          issued_on: date | None = Form(None), expires_on: date | None = Form(None),
                          p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    s = _load(db, sid)
    own = s.organization_id in _own_supplier_ids(p)
    if not own:  # helpdesk / field officers doing assisted registration
        ensure_in_scope(db, p, "sup:create", s.county_id)
    if doc_type not in DOC_TYPES:
        raise AppError(422, "VALIDATION_ERROR", "Unknown document type.")
    if expires_on and issued_on and expires_on <= issued_on:
        raise AppError(422, "VALIDATION_ERROR", "Expiry date must be after the issue date.")
    meta = await storage.save_upload(file, f"suppliers/{s.id}")
    prev = db.scalar(select(func.max(SupplierDocument.version)).where(SupplierDocument.supplier_id == s.id,
                                                                     SupplierDocument.doc_type == doc_type)) or 0
    d = SupplierDocument(supplier_id=s.id, doc_type=doc_type, version=prev + 1, issued_on=issued_on,
                         expires_on=expires_on, created_by=p.id, **meta)
    db.add(d)
    db.flush()
    audit.record(db, action="UPLOAD", entity="supplier_document", entity_id=d.id, user=p.user,
                 after={"supplier": str(s.id), "doc_type": doc_type, "version": d.version, "sha256": d.sha256},
                 request=request)
    db.commit()
    return d


@router.get("/{sid}/documents/{did}/file")
def download_document(sid: uuid.UUID, did: uuid.UUID, p: Principal = Depends(current_principal),
                      db: Session = Depends(get_db)):
    s = _load(db, sid)
    _can_see(db, p, s)
    d = db.get(SupplierDocument, did)
    if d is None or d.supplier_id != s.id:
        raise AppError(404, "NOT_FOUND", "Document not found.")
    return FileResponse(storage.open_path(d.file_key), media_type=d.content_type, filename=d.file_name)


@router.post("/{sid}/documents/{did}/review", response_model=DocOut)
def review_document(sid: uuid.UUID, did: uuid.UUID, body: DocReviewIn, request: Request,
                    p: Principal = Depends(require("sup:verify")), db: Session = Depends(get_db)):
    s = _load(db, sid)
    ensure_in_scope(db, p, "sup:verify", s.county_id)
    d = db.get(SupplierDocument, did)
    if d is None or d.supplier_id != s.id:
        raise AppError(404, "NOT_FOUND", "Document not found.")
    before = d.status.value
    d.status, d.review_note, d.updated_by = body.status, body.note, p.id
    audit.record(db, action="VERIFY" if body.status == DocumentStatus.verified else "REJECT",
                 entity="supplier_document", entity_id=d.id, user=p.user, before={"status": before},
                 after={"status": body.status.value}, reason=body.note, request=request)
    db.commit()
    return d


@router.post("/{sid}/inclusion", response_model=SupplierOut)
def verify_inclusion(sid: uuid.UUID, body: InclusionVerifyIn, request: Request,
                     p: Principal = Depends(require("sup:verify")), db: Session = Depends(get_db)):
    """BR-014: inclusion status counts only after an officer verifies it."""
    s = _load(db, sid)
    ensure_in_scope(db, p, "sup:verify", s.county_id)
    if not s.inclusion_consent:
        raise AppError(409, "NO_CONSENT", "The supplier has not consented to sharing inclusion information.")
    s.inclusion_verified = body.verified
    s.inclusion_verified_by, s.inclusion_verified_at = p.id, utcnow()
    audit.record(db, action="VERIFY_INCLUSION", entity="supplier", entity_id=s.id, user=p.user,
                 after={"verified": body.verified, "claim": s.inclusion_claim}, reason=body.note, request=request)
    db.commit()
    return _out(s)


@router.post("/{sid}/review", response_model=SupplierOut)
def review(sid: uuid.UUID, body: ReviewIn, request: Request, p: Principal = Depends(current_principal),
           db: Session = Depends(get_db)):
    s = _load(db, sid)
    if s.organization_id in _own_supplier_ids(p):
        raise AppError(403, "SOD_CONFLICT", "You cannot review your own supplier record (SoD-04).")
    ensure_in_scope(db, p, "sup:view", s.county_id)
    if body.to_status not in SUPPLIER_TRANSITIONS.get(s.status, set()):
        raise AppError(409, "INVALID_TRANSITION", f"A supplier cannot move from '{s.status.value}' to '{body.to_status.value}'.")
    ensure_in_scope(db, p, NEEDS.get(body.to_status, "sup:approve"), s.county_id)
    if body.to_status in (SupplierStatus.approved, SupplierStatus.prequalified):
        latest = {}
        for d in s.documents:
            if d.doc_type not in latest or d.version > latest[d.doc_type].version:
                latest[d.doc_type] = d
        missing = [DOC_TYPES[t] for t in REQUIRED_DOCS if t not in latest or latest[t].status != DocumentStatus.verified]
        if missing:
            raise AppError(409, "DOCUMENTS_INCOMPLETE", "Verify the required documents first: " + ", ".join(missing) + ".")
    if body.to_status == SupplierStatus.prequalified:
        if not body.approved_categories:
            raise AppError(422, "VALIDATION_ERROR", "Choose the commodity categories this supplier is prequalified for.")
        from app.seed.reference import CATEGORY_LABELS
        unknown = sorted(set(body.approved_categories) - set(CATEGORY_LABELS))
        if unknown:
            raise AppError(422, "VALIDATION_ERROR", "Unknown food categories: " + ", ".join(unknown) + ".")
        s.approved_categories = body.approved_categories
        s.prequalified_until = body.prequalified_until
    before = s.status.value
    s.status, s.status_note, s.updated_by = body.to_status, body.note, p.id
    audit.record(db, action=body.to_status.value.upper(), entity="supplier", entity_id=s.id, user=p.user,
                 before={"status": before}, after={"status": s.status.value, "categories": s.approved_categories},
                 reason=body.note, request=request)
    db.commit()
    return _out(s)
