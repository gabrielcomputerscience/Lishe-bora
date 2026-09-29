import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models import AuditLog, User

REDACT = {"password", "password_hash", "code", "code_hash", "refresh_hash", "kra_pin"}


def _clean(v):
    if isinstance(v, dict):
        return {k: ("***" if k in REDACT else _clean(x)) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (uuid.UUID, Decimal)):
        return str(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Enum):
        return v.value
    return v


def snapshot(obj, fields: list[str]) -> dict:
    return _clean({f: getattr(obj, f, None) for f in fields})


def record(db: Session, *, action: str, entity: str, entity_id="", user: User | None = None,
           before: dict | None = None, after: dict | None = None, reason: str = "", request: Request | None = None):
    """Write an audit row in the caller's transaction (commit happens with the business change)."""
    roles = ""
    if user is not None:
        roles = ",".join(sorted({ur.role.key for ur in user.roles if ur.is_active}))
    db.add(AuditLog(
        at=utcnow(), user_id=user.id if user else None,
        user_label=(user.email or user.phone or user.full_name) if user else "system", roles=roles,
        action=action, entity=entity, entity_id=str(entity_id),
        before=_clean(before) if before else None, after=_clean(after) if after else None, reason=reason,
        ip=(request.client.host if request and request.client else ""),
        user_agent=(request.headers.get("user-agent", "")[:300] if request else ""),
        correlation_id=(getattr(request.state, "correlation_id", "") if request else ""),
    ))
