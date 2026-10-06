"""Features & menus: the Super Administrator decides which portal pages each role, and each person, sees."""
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.deps import Principal, require
from app.core.errors import AppError
from app.models import Role, RolePermission, User, UserRole
from app.services import audit
from app.services import menu as m
from app.services.admin_access import is_super

router = APIRouter(tags=["features"])


def super_only(p: Principal = Depends(require("iam:edit"))) -> Principal:
    if not is_super(p.user):
        raise AppError(403, "SUPER_ADMIN_ONLY", "Only the Super Administrator can change features and menus.")
    return p


class PagesIn(BaseModel):
    pages: list[str]


class UserFeaturesIn(BaseModel):
    add: list[str] = []
    remove: list[str] = []


def _check(pages: list[str]):
    bad = [x for x in pages if x not in m.FEATURES]
    if bad:
        raise AppError(422, "VALIDATION_ERROR", f"Unknown page(s): {', '.join(bad)}")


def _catalog():
    return [{"page": k, "label": v[0], "group": v[1], "permissions": list(v[2]), "audience": v[3]} for k, v in m.FEATURES.items()]


@router.get("/features")
def features(p: Principal = Depends(super_only), db: Session = Depends(get_db)):
    roles = db.scalars(select(Role).options(selectinload(Role.permissions).selectinload(RolePermission.permission)).order_by(Role.tier, Role.name)).all()
    over = m._setting(db, "menu.roles")
    out = []
    for r in roles:
        perms = {rp.permission.code for rp in r.permissions}
        sup_role = r.key in ("supplier", "farmer_group", "aggregator")
        out.append({"key": r.key, "name": r.name, "pages": m.role_pages(db, r.key), "customised": r.key in over,
                    "possible": [k for k in m.FEATURES if m.allowed(k, perms, sup_role, r.key == "super_admin")]})
    return {"catalog": _catalog(), "roles": out}


@router.put("/features/roles/{key}")
def set_role_pages(key: str, body: PagesIn, request: Request, p: Principal = Depends(super_only), db: Session = Depends(get_db)):
    role = db.scalar(select(Role).where(Role.key == key))
    if role is None:
        raise AppError(404, "NOT_FOUND", "Role not found.")
    _check(body.pages)
    if key == "super_admin" and "/app/features" not in body.pages:
        raise AppError(422, "VALIDATION_ERROR", "The Super Administrator must keep ‘Features & menus’.")
    over = m._setting(db, "menu.roles")
    before = over.get(key, m.ROLE_DEFAULTS.get(key, []))
    over[key] = [x for x in m.FEATURES if x in set(body.pages)]
    m.save_setting(db, "menu.roles", over, "Portal pages per role (changed by the Super Administrator)")
    audit.record(db, action="ROLE_MENU", entity="role", entity_id=role.id, user=p.user, before={"pages": before}, after={"pages": over[key]},
                 request=request)
    db.commit()
    return {"key": key, "pages": over[key], "customised": True}


@router.post("/features/roles/{key}/reset")
def reset_role_pages(key: str, request: Request, p: Principal = Depends(super_only), db: Session = Depends(get_db)):
    over = m._setting(db, "menu.roles")
    if key in over:
        before = over.pop(key)
        m.save_setting(db, "menu.roles", over, "Portal pages per role (changed by the Super Administrator)")
        role = db.scalar(select(Role).where(Role.key == key))
        audit.record(db, action="ROLE_MENU_RESET", entity="role", entity_id=role.id if role else None, user=p.user, before={"pages": before},
                     request=request)
        db.commit()
    return {"key": key, "pages": m.ROLE_DEFAULTS.get(key, []), "customised": False}


def _user(db: Session, uid: uuid.UUID) -> User:
    u = db.scalar(select(User).where(User.id == uid).options(selectinload(User.roles).selectinload(UserRole.role)
                                                              .selectinload(Role.permissions).selectinload(RolePermission.permission)))
    if u is None:
        raise AppError(404, "NOT_FOUND", "User not found.")
    return u


@router.get("/users/{uid}/features")
def user_features(uid: uuid.UUID, p: Principal = Depends(super_only), db: Session = Depends(get_db)):
    u = _user(db, uid)
    keys = [ur.role.key for ur in u.roles if ur.is_active]
    perms, supplier = m.user_permissions(u), m.is_supplier_account(db, u)
    defaults = {x for k in keys for x in m.role_pages(db, k)}
    ov = m.user_overrides(db, u.id)
    added, removed = set(ov.get("add", [])), set(ov.get("remove", []))
    rows = []
    for k, (label, group, need, aud) in m.FEATURES.items():
        ok = m.allowed(k, perms, supplier, "super_admin" in keys)
        status = ("removed" if k in removed else "default" if k in defaults else "added" if k in added else "available") if ok else "needs_role"
        rows.append({"page": k, "label": label, "group": group, "status": status, "shown": ok and k not in removed and (k in defaults or k in added),
                     "needs": [] if ok or aud in ("supplier", "super") else m.who_has(db, need)[:6],
                     "note": {"supplier": "Supplier accounts only", "super": "Super Administrator only", "staff": ""}.get(aud, "") if not ok else ""})
    return {"user": {"id": u.id, "full_name": u.full_name, "email": u.email, "roles": keys}, "pages": rows, "menu": m.menu_for(db, u)}


@router.put("/users/{uid}/features")
def set_user_features(uid: uuid.UUID, body: UserFeaturesIn, request: Request, p: Principal = Depends(super_only), db: Session = Depends(get_db)):
    u = _user(db, uid)
    _check(body.add + body.remove)
    perms, supplier = m.user_permissions(u), m.is_supplier_account(db, u)
    sup = "super_admin" in {ur.role.key for ur in u.roles if ur.is_active}
    blocked = [m.FEATURES[x][0] for x in body.add if not m.allowed(x, perms, supplier, sup)]
    if blocked:
        raise AppError(422, "NEEDS_ROLE", f"{u.full_name}'s roles do not allow: {', '.join(blocked)}. Assign a role that includes it under "
                                          "Users & roles first; adding a page never adds rights.")
    if u.id == p.id and "/app/features" in body.remove:
        raise AppError(422, "VALIDATION_ERROR", "You cannot remove ‘Features & menus’ from your own account.")
    users = m._setting(db, "menu.users")
    before = users.get(str(u.id))
    new = {"add": sorted(set(body.add) - set(body.remove)), "remove": sorted(set(body.remove))}
    if new["add"] or new["remove"]:
        users[str(u.id)] = new
    else:
        users.pop(str(u.id), None)
    m.save_setting(db, "menu.users", users, "Extra or hidden portal pages per user (changed by the Super Administrator)")
    audit.record(db, action="USER_MENU", entity="user", entity_id=u.id, user=p.user, before={"features": before}, after={"features": new},
                 request=request)
    db.commit()
    return user_features(uid, p, db)
