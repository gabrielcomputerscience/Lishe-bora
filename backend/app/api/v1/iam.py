"""Users & roles administration (FR-IAM-02/05/06/07)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, require, scope_for
from app.core.errors import AppError
from app.core.security import hash_password, new_opaque_token
from app.models import Organization, Role, RolePermission, User, UserRole, UserStatus
from app.schemas.common import Msg, PhoneMixin
from app.seed.matrix import CONFLICTING_ROLE_PAIRS
from app.services import audit
from app.services.admin_access import ADMIN_ROLES, check_can_manage, check_role_mix, is_admin_account
from app.services import notify

router = APIRouter(tags=["users & roles"])


class RoleOut(BaseModel):
    key: str
    name: str
    tier: str
    default_scope: str
    requires_mfa: bool
    permissions: list[str]


class UserRoleOut(BaseModel):
    id: uuid.UUID
    role: str
    role_name: str
    org_id: uuid.UUID | None
    org_name: str | None
    valid_to: datetime | None
    delegated_from: uuid.UUID | None


class UserOut(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    status: str
    last_login_at: datetime | None
    roles: list[UserRoleOut]


class InviteIn(PhoneMixin):
    full_name: str = Field(min_length=2)
    email: EmailStr | None = None
    phone: str | None = None
    role: str
    org_id: uuid.UUID | None = None


class AssignIn(BaseModel):
    role: str
    org_id: uuid.UUID | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    reason: str = ""


class StatusIn(BaseModel):
    status: UserStatus
    reason: str = ""


def _user_out(db: Session, u: User) -> UserOut:
    rs = []
    for ur in u.roles:
        if ur.is_active:
            org = db.get(Organization, ur.org_id) if ur.org_id else None
            rs.append(UserRoleOut(id=ur.id, role=ur.role.key, role_name=ur.role.name, org_id=ur.org_id,
                                  org_name=org.name if org else None, valid_to=ur.valid_to,
                                  delegated_from=ur.delegated_from))
    return UserOut(id=u.id, full_name=u.full_name, email=u.email, phone=u.phone, status=u.status.value,
                   last_login_at=u.last_login_at, roles=rs)


def check_sod(existing: set[str], new_role: str):
    for a, b in CONFLICTING_ROLE_PAIRS:
        if (new_role == a and b in existing) or (new_role == b and a in existing):
            raise AppError(409, "SOD_CONFLICT",
                           f"Segregation of duties: one person cannot hold both '{a}' and '{b}'.")


@router.get("/roles", response_model=list[RoleOut])
def list_roles(p: Principal = Depends(require("iam:view")), db: Session = Depends(get_db)):
    roles = db.scalars(select(Role).options(selectinload(Role.permissions).selectinload(RolePermission.permission))
                       .order_by(Role.tier, Role.name)).all()
    return [RoleOut(key=r.key, name=r.name, tier=r.tier, default_scope=r.default_scope, requires_mfa=r.requires_mfa,
                    permissions=sorted(rp.permission.code for rp in r.permissions)) for r in roles]


@router.get("/users")
def list_users(q: str = "", role: str = "", status: str = "", page: int = Query(1, ge=1),
               size: int = Query(25, ge=1, le=100),
               p: Principal = Depends(require("iam:view")), db: Session = Depends(get_db)):
    stmt = select(User).options(selectinload(User.roles).selectinload(UserRole.role))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like), User.phone.like(like)))
    if status:
        stmt = stmt.where(User.status == UserStatus(status))
    if role:
        stmt = stmt.where(User.roles.any(UserRole.role.has(Role.key == role)))
    allowed = scope_for(db, p, "iam:view")
    if allowed is not None:  # scoped admins only see users assigned inside their area
        stmt = stmt.where(User.roles.any(UserRole.org_id.in_(allowed)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(User.full_name).offset((page - 1) * size).limit(size)).unique().all()
    return {"total": total, "items": [_user_out(db, u) for u in rows]}


@router.post("/users/invite", response_model=UserOut, status_code=201)
def invite(body: InviteIn, request: Request, p: Principal = Depends(require("iam:create")), db: Session = Depends(get_db)):
    """Staff and school accounts are invitation-only. A temporary password is sent; user must change it."""
    if not body.email and not body.phone:
        raise AppError(422, "VALIDATION_ERROR", "Provide an email or a mobile number.")
    if body.email and db.scalar(select(User).where(User.email == body.email.lower())):
        raise AppError(409, "EMAIL_IN_USE", "A user with this email already exists.")
    if body.phone and db.scalar(select(User).where(User.phone == body.phone)):
        raise AppError(409, "PHONE_IN_USE", "A user with this mobile number already exists.")
    role = db.scalar(select(Role).where(Role.key == body.role))
    if role is None:
        raise AppError(422, "VALIDATION_ERROR", "Unknown role.")
    check_can_manage(p.user, role_key=role.key)
    if role.key in ADMIN_ROLES:
        body.org_id = None            # administrators are national
    temp = new_opaque_token()[:14] + "A1"
    u = User(full_name=body.full_name, email=body.email.lower() if body.email else None, phone=body.phone,
             password_hash=hash_password(temp), status=UserStatus.active, created_by=p.id)
    db.add(u)
    db.flush()
    db.add(UserRole(user_id=u.id, role_id=role.id, org_id=body.org_id, created_by=p.id))
    audit.record(db, action="INVITE", entity="user", entity_id=u.id, user=p.user,
                 after={"full_name": u.full_name, "role": role.key, "org_id": body.org_id}, request=request)
    where = " Sign in at the administration sign-in page (/admin/sign-in)." if role.key in ADMIN_ROLES else ""
    msg = f"You have been invited to LisheBora as {role.name}. Temporary password: {temp} (change it after signing in).{where}"
    if u.email:
        notify.email(db, u.email, "LisheBora invitation", msg, sensitive=True, urgent=True)
    else:
        notify.sms(db, u.phone, msg, sensitive=True, urgent=True)
    db.commit()
    db.refresh(u)
    return _user_out(db, u)


@router.post("/users/{user_id}/roles", response_model=UserOut)
def assign_role(user_id: uuid.UUID, body: AssignIn, request: Request, p: Principal = Depends(require("iam:edit")),
                db: Session = Depends(get_db)):
    if user_id == p.id:
        raise AppError(403, "SOD_SELF_ASSIGN", "You cannot change your own roles (SoD-11).")
    u = db.get(User, user_id)
    role = db.scalar(select(Role).where(Role.key == body.role))
    if u is None or role is None:
        raise AppError(404, "NOT_FOUND", "User or role not found.")
    check_can_manage(p.user, target=u, role_key=role.key)
    have = {ur.role.key for ur in u.roles if ur.is_active}
    check_role_mix(have, role.key)
    check_sod(have, role.key)
    if body.org_id and db.get(Organization, body.org_id) is None:
        raise AppError(422, "VALIDATION_ERROR", "Unknown organisation.")
    ur = UserRole(user_id=u.id, role_id=role.id, org_id=body.org_id, valid_from=body.valid_from,
                  valid_to=body.valid_to, created_by=p.id)
    db.add(ur)
    audit.record(db, action="ROLE_ASSIGN", entity="user", entity_id=u.id, user=p.user,
                 after={"role": role.key, "org_id": body.org_id, "valid_to": body.valid_to}, reason=body.reason,
                 request=request)
    db.commit()
    db.refresh(u)
    return _user_out(db, u)


@router.delete("/users/{user_id}/roles/{assignment_id}", response_model=Msg)
def revoke_role(user_id: uuid.UUID, assignment_id: uuid.UUID, request: Request,
                p: Principal = Depends(require("iam:edit")), db: Session = Depends(get_db)):
    if user_id == p.id:
        raise AppError(403, "SOD_SELF_ASSIGN", "You cannot change your own roles (SoD-11).")
    ur = db.get(UserRole, assignment_id)
    if ur is None or ur.user_id != user_id:
        raise AppError(404, "NOT_FOUND", "Assignment not found.")
    check_can_manage(p.user, target=db.get(User, user_id), role_key=ur.role.key)
    ur.is_active = False
    audit.record(db, action="ROLE_REVOKE", entity="user", entity_id=user_id, user=p.user,
                 before={"role": ur.role.key, "org_id": ur.org_id}, request=request)
    db.commit()
    return Msg(message="Role removed.")


@router.post("/users/{user_id}/status", response_model=UserOut)
def set_status(user_id: uuid.UUID, body: StatusIn, request: Request, p: Principal = Depends(require("iam:edit")),
               db: Session = Depends(get_db)):
    if user_id == p.id:
        raise AppError(403, "FORBIDDEN", "You cannot change your own account status.")
    u = db.get(User, user_id)
    if u is None:
        raise AppError(404, "NOT_FOUND", "User not found.")
    check_can_manage(p.user, target=u)
    before = u.status.value
    u.status = body.status
    audit.record(db, action="STATUS", entity="user", entity_id=u.id, user=p.user, before={"status": before},
                 after={"status": body.status.value}, reason=body.reason, request=request)
    db.commit()
    return _user_out(db, u)
