"""Human-readable sequential references (e.g. BATCH-2026-000145)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow


def next_ref(db: Session, model, prefix: str, width: int = 5) -> str:
    n = (db.scalar(select(func.count()).select_from(model)) or 0) + 1
    ref = f"{prefix}-{utcnow():%Y}-{n:0{width}d}"
    col = getattr(model, "code", None) or getattr(model, "reference")
    while db.scalar(select(func.count()).select_from(model).where(col == ref)):
        n += 1
        ref = f"{prefix}-{utcnow():%Y}-{n:0{width}d}"
    return ref
