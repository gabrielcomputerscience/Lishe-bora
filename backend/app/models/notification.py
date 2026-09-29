import uuid
from datetime import datetime

from app.models.types import UTCDateTime
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin


class Notification(IdMixin, Base):
    """In-app notification (FR-PLT-02). SMS/email copies go through services.notify."""
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(300), default="")
    event: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class OutboundMessage(IdMixin, Base):
    """SMS / email outbox. Messages are queued in the same transaction as the business change and delivered by the
    provider adapter (immediately for sign-in codes, otherwise by the background worker with retries)."""
    __tablename__ = "outbound_messages"

    channel: Mapped[str] = mapped_column(String(8), index=True)          # sms | email
    to: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text)
    sensitive: Mapped[bool] = mapped_column(default=False)               # codes / passwords: body is wiped once sent
    status: Mapped[str] = mapped_column(String(12), default="queued", index=True)   # queued | sent | failed
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str] = mapped_column(String(500), default="")
    provider: Mapped[str] = mapped_column(String(30), default="")
    provider_ref: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
