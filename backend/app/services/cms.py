import re
import unicodedata

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import AppError
from app.core.timeutil import utcnow
from app.models import ContentStatus, ContentVersion

# draft → in_review → published; published → archived/draft; in_review → draft (returned)
FLOW = {
    "submit": ({ContentStatus.draft}, ContentStatus.in_review, "cms:submit"),
    "return": ({ContentStatus.in_review}, ContentStatus.draft, "cms:reject"),
    "publish": ({ContentStatus.draft, ContentStatus.in_review}, ContentStatus.published, "cms:approve"),
    "unpublish": ({ContentStatus.published}, ContentStatus.draft, "cms:approve"),
    "archive": ({ContentStatus.published, ContentStatus.draft}, ContentStatus.archived, "cms:approve"),
}


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:150] or "item"


def unique_slug(db: Session, model, base: str, exclude_id=None) -> str:
    slug, n = base, 2
    while True:
        q = select(model.id).where(model.slug == slug)
        if exclude_id:
            q = q.where(model.id != exclude_id)
        if db.scalar(q) is None:
            return slug
        slug, n = f"{base}-{n}", n + 1


def transition(obj, action: str, p: Principal, note: str = ""):
    if action not in FLOW:
        raise AppError(422, "VALIDATION_ERROR", "Unknown action.")
    allowed_from, to, perm = FLOW[action]
    if not p.can(perm):
        raise AppError(403, "FORBIDDEN", "You do not have permission to do this.")
    if obj.status not in allowed_from:
        raise AppError(409, "INVALID_TRANSITION", f"Cannot {action} content that is '{obj.status.value}'.")
    obj.status = to
    obj.review_note = note
    if action == "submit":
        obj.submitted_by = p.id
    if action == "publish":
        obj.published_at, obj.published_by = utcnow(), p.id
    return to


def save_version(db: Session, entity: str, obj, snapshot: dict, p: Principal):
    last = db.scalar(select(func.max(ContentVersion.version)).where(ContentVersion.entity == entity,
                                                                   ContentVersion.entity_id == obj.id)) or 0
    obj.version = last + 1
    db.add(ContentVersion(entity=entity, entity_id=obj.id, version=obj.version, status=obj.status.value,
                          snapshot=snapshot, created_at=utcnow(), created_by=p.id))
