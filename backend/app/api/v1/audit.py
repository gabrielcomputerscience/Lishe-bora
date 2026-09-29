from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, require
from app.models import AuditLog

router = APIRouter(tags=["audit"])


@router.get("/audit")
def list_audit(entity: str = "", entity_id: str = "", action: str = "", since: datetime | None = None,
               page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
               p: Principal = Depends(require("aud:view")), db: Session = Depends(get_db)):
    """Read-only. There are intentionally no write endpoints for the audit log."""
    stmt = select(AuditLog)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action.upper())
    if since:
        stmt = stmt.where(AuditLog.at >= since)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.at.desc()).offset((page - 1) * size).limit(size)).all()
    return {"total": total, "items": [
        {"id": r.id, "at": r.at, "user": r.user_label, "roles": r.roles, "action": r.action, "entity": r.entity,
         "entity_id": r.entity_id, "before": r.before, "after": r.after, "reason": r.reason, "ip": r.ip,
         "correlation_id": r.correlation_id} for r in rows]}
