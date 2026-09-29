"""Authentication, permission and data-scope dependencies.

Permission model (SRS §6.2): User → Role → Organisation/Data scope → Permission.
Authorization is enforced here at the API, never only in the UI (SRS §10.1)."""
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import decode_token
from app.core.timeutil import as_utc, utcnow
from app.models import Organization, Role, RolePermission, User, UserRole, UserStatus

ACCESS_COOKIE = "lb_access"
REFRESH_COOKIE = "lb_refresh"


@dataclass
class Principal:
    user: User
    # permission code -> list of org scopes (None = national / unrestricted)
    grants: dict[str, list[uuid.UUID | None]] = field(default_factory=dict)

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    def can(self, code: str) -> bool:
        return code in self.grants

    @property
    def role_keys(self) -> set[str]:
        return {ur.role.key for ur in self.user.roles if ur.is_active}


def _token_from(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


def load_principal(db: Session, user_id: uuid.UUID) -> Principal | None:
    user = db.scalar(
        select(User).where(User.id == user_id).options(
            selectinload(User.roles).selectinload(UserRole.role)
            .selectinload(Role.permissions).selectinload(RolePermission.permission)))
    if user is None:
        return None
    now = utcnow()
    grants: dict[str, list] = {}
    for ur in user.roles:
        if not ur.is_active or not ur.role.is_active:
            continue
        if ur.valid_from and as_utc(ur.valid_from) > now:
            continue
        if ur.valid_to and as_utc(ur.valid_to) < now:
            continue
        for rp in ur.role.permissions:
            grants.setdefault(rp.permission.code, []).append(ur.org_id)
    return Principal(user=user, grants=grants)


def optional_principal(request: Request, db: Session = Depends(get_db)) -> Principal | None:
    token = _token_from(request)
    if not token:
        return None
    try:
        data = decode_token(token, "access")
    except jwt.PyJWTError:
        return None
    p = load_principal(db, uuid.UUID(data["sub"]))
    if p is None or p.user.status != UserStatus.active:
        return None
    request.state.user_id = p.user.id
    return p


def current_principal(p: Principal | None = Depends(optional_principal)) -> Principal:
    if p is None:
        raise AppError(401, "UNAUTHENTICATED", "Please sign in.")
    return p


def require(*codes: str) -> Callable[..., Principal]:
    """Dependency: user must hold ALL listed permission codes (in some scope)."""
    def _dep(p: Principal = Depends(current_principal)) -> Principal:
        missing = [c for c in codes if not p.can(c)]
        if missing:
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.", [{"missing": missing}])
        return p
    return _dep


def require_any(*codes: str) -> Callable[..., Principal]:
    """Dependency: user must hold AT LEAST ONE of the listed permission codes."""
    def _dep(p: Principal = Depends(current_principal)) -> Principal:
        if not any(p.can(c) for c in codes):
            raise AppError(403, "FORBIDDEN", "You do not have permission to do this.", [{"any_of": list(codes)}])
        return p
    return _dep


def scope_any(db: Session, p: Principal, *codes: str) -> set[uuid.UUID] | None:
    """Union of scopes over several permission codes (None = national on any of them)."""
    out: set[uuid.UUID] = set()
    for c in codes:
        if not p.can(c):
            continue
        s = scope_for(db, p, c)
        if s is None:
            return None
        out |= s
    return out


def descendants(db: Session, root_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """All org ids at or below the given roots (county → sub-counties → schools…)."""
    found = set(root_ids)
    frontier = list(root_ids)
    while frontier:
        kids = db.scalars(select(Organization.id).where(Organization.parent_id.in_(frontier))).all()
        frontier = [k for k in kids if k not in found]
        found.update(frontier)
    return found


def scope_for(db: Session, p: Principal, code: str) -> set[uuid.UUID] | None:
    """Returns None when the user holds `code` nationally (no filter), otherwise the set of org ids in scope."""
    scopes = p.grants.get(code, [])
    if any(s is None for s in scopes):
        return None
    return descendants(db, [s for s in scopes if s is not None])


def ensure_in_scope(db: Session, p: Principal, code: str, *org_ids: uuid.UUID | None) -> None:
    if not p.can(code):
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    allowed = scope_for(db, p, code)
    if allowed is None:
        return
    if not any(o in allowed for o in org_ids if o is not None):
        raise AppError(403, "OUT_OF_SCOPE", "This record is outside your assigned area.")
