import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require
from app.core.errors import AppError
from app.models import Commodity, Organization, OrgType
from app.schemas.common import ORM, OrgOut
from app.services import audit

router = APIRouter(tags=["master data"])


class OrgIn(BaseModel):
    type: OrgType
    name: str = Field(min_length=2)
    code: str = Field(min_length=2, max_length=50)
    parent_id: uuid.UUID | None = None
    meta: dict = Field(default_factory=dict)


class CommodityIn(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str
    category: str
    unit: str = "kg"
    standard_pack: str = ""
    food_group: str = ""
    quality_spec: dict = Field(default_factory=dict)
    default_portion_g: Decimal | None = None
    reference_price: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True


class CommodityOut(ORM, CommodityIn):
    id: uuid.UUID


def _check_category(body: CommodityIn):
    from app.seed.reference import CATEGORY_LABELS, FOOD_CATEGORIES
    if body.category not in CATEGORY_LABELS:
        raise AppError(422, "VALIDATION_ERROR", "Choose one of the programme food categories.",
                       [{"field": "category", "message": "Unknown food category"}])
    if not body.food_group:     # default to the category's nutrition group
        body.food_group = next(g for k, _l, g, _i in FOOD_CATEGORIES if k == body.category)


@router.get("/orgs", response_model=list[OrgOut])
def list_orgs(type: OrgType | None = None, parent_id: uuid.UUID | None = None,
              p: Principal = Depends(require("md:view")), db: Session = Depends(get_db)):
    stmt = select(Organization).where(Organization.type != OrgType.supplier)
    if type:
        stmt = stmt.where(Organization.type == type)
    if parent_id:
        stmt = stmt.where(Organization.parent_id == parent_id)
    return db.scalars(stmt.order_by(Organization.name)).all()


@router.post("/orgs", response_model=OrgOut, status_code=201)
def create_org(body: OrgIn, request: Request, p: Principal = Depends(require("md:create")), db: Session = Depends(get_db)):
    if db.scalar(select(Organization).where(Organization.code == body.code)):
        raise AppError(409, "CODE_IN_USE", "An organisation with this code already exists.")
    o = Organization(**body.model_dump(), created_by=p.id)
    db.add(o)
    db.flush()
    audit.record(db, action="CREATE", entity="organization", entity_id=o.id, user=p.user, after=body.model_dump(),
                 request=request)
    db.commit()
    return o


@router.get("/commodities", response_model=list[CommodityOut])
def list_commodities(db: Session = Depends(get_db), p: Principal = Depends(require("md:view"))):
    return db.scalars(select(Commodity).order_by(Commodity.category, Commodity.name)).all()


@router.post("/commodities", response_model=CommodityOut, status_code=201)
def create_commodity(body: CommodityIn, request: Request, p: Principal = Depends(require("md:create")),
                     db: Session = Depends(get_db)):
    body.code = body.code.strip().upper()
    if db.scalar(select(Commodity).where(Commodity.code == body.code)):
        raise AppError(409, "CODE_IN_USE", "A commodity with this code already exists.")
    _check_category(body)
    c = Commodity(**body.model_dump(), created_by=p.id)
    db.add(c)
    db.flush()
    audit.record(db, action="CREATE", entity="commodity", entity_id=c.id, user=p.user, after=body.model_dump(),
                 request=request)
    db.commit()
    return c


@router.put("/commodities/{cid}", response_model=CommodityOut)
def update_commodity(cid: uuid.UUID, body: CommodityIn, request: Request, p: Principal = Depends(require("md:edit")),
                     db: Session = Depends(get_db)):
    c = db.get(Commodity, cid)
    if c is None:
        raise AppError(404, "NOT_FOUND", "Commodity not found.")
    if body.code != c.code:
        raise AppError(409, "CODE_FIXED", "A commodity code cannot change once created (orders and stock refer to it).")
    _check_category(body)
    before = audit.snapshot(c, list(CommodityIn.model_fields))
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    c.updated_by = p.id
    audit.record(db, action="UPDATE", entity="commodity", entity_id=c.id, user=p.user, before=before,
                 after=body.model_dump(), request=request)
    db.commit()
    return c


class OrgUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    code: str | None = Field(default=None, min_length=2, max_length=50)
    is_active: bool | None = None


@router.put("/orgs/{oid}", response_model=OrgOut)
def update_org(oid: uuid.UUID, body: OrgUpdate, request: Request, p: Principal = Depends(require("md:edit")), db: Session = Depends(get_db)):
    """Rename an organisation, change its code (e.g. to the school's NEMIS code) or deactivate it. Records link by id,
    so a new code keeps every order, delivery and user linked."""
    o = db.get(Organization, oid)
    if o is None or o.type == OrgType.supplier:
        raise AppError(404, "NOT_FOUND", "Organisation not found.")
    before = {"name": o.name, "code": o.code, "is_active": o.is_active}
    o.name = body.name.strip()
    if body.code and body.code.strip().upper() != o.code:
        code = body.code.strip().upper()
        if db.scalar(select(Organization.id).where(Organization.code == code)):
            raise AppError(409, "CODE_IN_USE", "Another organisation already uses this code.")
        o.code = code
    if body.is_active is not None:
        o.is_active = body.is_active
    audit.record(db, action="UPDATE", entity="organization", entity_id=o.id, user=p.user, before=before,
                 after={"name": o.name, "code": o.code, "is_active": o.is_active}, request=request)
    db.commit()
    return o
