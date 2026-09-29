"""Integration transaction log (FR-PLT-06, SRS §10.2): every file exchanged with a bank, M-Pesa or IFMIS and every
callback received is recorded with its outcome, so reconciliation can be audited."""
import uuid

from sqlalchemy import JSON, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class IntegrationTransaction(IdMixin, TimestampMixin, Base):
    __tablename__ = "integration_transactions"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)      # INT-2026-00001
    direction: Mapped[str] = mapped_column(String(8))                                # out | in
    system: Mapped[str] = mapped_column(String(20), index=True)                      # bank | mpesa | ifmis
    kind: Mapped[str] = mapped_column(String(30))                                    # payment_file | statement_import | callback | ifmis_export
    status: Mapped[str] = mapped_column(String(20), default="completed")             # completed | partial | failed
    county_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    file_key: Mapped[str] = mapped_column(String(300), default="")
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
