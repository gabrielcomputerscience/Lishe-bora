"""Event-driven notifications (FR-PLT-02): in-app row + SMS/email copy via services.notify."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models import Notification, Role, User, UserRole, UserStatus
from app.services import notify


def to_users(db: Session, user_ids, title: str, body: str = "", link: str = "", event: str = "", sms: bool = False):
    now = utcnow()
    for uid in set(user_ids):
        db.add(Notification(user_id=uid, title=title, body=body, link=link, event=event, created_at=now))
        if sms:
            u = db.get(User, uid)
            if u and u.phone:
                notify.sms(db, u.phone, f"LisheBora: {title}. {body}"[:300])
            elif u and u.email:
                notify.email(db, u.email, f"LisheBora: {title}", body)


def users_of_org(db: Session, org_id: uuid.UUID) -> list[uuid.UUID]:
    return list(db.scalars(select(UserRole.user_id).join(User, User.id == UserRole.user_id)
                           .where(UserRole.org_id == org_id, UserRole.is_active, User.status == UserStatus.active)))


def users_with_role(db: Session, role_key: str, org_id=None) -> list[uuid.UUID]:
    q = (select(UserRole.user_id).join(Role, Role.id == UserRole.role_id)
         .where(Role.key == role_key, UserRole.is_active))
    if org_id is not None:
        q = q.where(UserRole.org_id == org_id)
    return list(db.scalars(q))


def users_with_permission(db: Session, code: str, org_id=None) -> list[uuid.UUID]:
    """Active users holding `code` whose role scope covers org_id (national roles always match)."""
    from app.core.deps import descendants
    from app.models import Permission, RolePermission
    rows = db.execute(select(UserRole.user_id, UserRole.org_id).join(User, User.id == UserRole.user_id)
                      .join(RolePermission, RolePermission.role_id == UserRole.role_id)
                      .join(Permission, Permission.id == RolePermission.permission_id)
                      .where(Permission.code == code, UserRole.is_active, User.status == UserStatus.active)).all()
    out = set()
    for uid, scope in rows:
        if scope is None or org_id is None or org_id in descendants(db, [scope]):
            out.add(uid)
    return list(out)
