import uuid
from datetime import datetime

from app.models.types import UTCDateTime
from sqlalchemy import JSON, DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class AuditLog(IdMixin, Base):
    """Append-only. No update/delete endpoints exist (BR-010, FR-PLT-04)."""
    __tablename__ = "audit_log"

    at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    user_label: Mapped[str] = mapped_column(String(200), default="system")
    roles: Mapped[str] = mapped_column(String(300), default="")
    action: Mapped[str] = mapped_column(String(40), index=True)          # CREATE, UPDATE, APPROVE, LOGIN…
    entity: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    correlation_id: Mapped[str] = mapped_column(String(64), default="")
