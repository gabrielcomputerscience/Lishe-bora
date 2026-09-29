"""Budget & commitment control (SRS §3.4, FR-BUD-01…07, BR-001, BR-008)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from app.models.types import UTCDateTime
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class FundingSource(IdMixin, TimestampMixin, Base):
    __tablename__ = "funding_sources"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40), default="grant")   # grant | county | national | other
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BudgetLine(IdMixin, TimestampMixin, Base):
    __tablename__ = "budget_lines"

    code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    funding_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("funding_sources.id"))
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)   # county or school
    term_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("academic_terms.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(60), default="")     # optional commodity category restriction
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    approved_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(String(3), default="KES")
    alert_threshold_pct: Mapped[int] = mapped_column(default=80)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    funding_source = relationship("FundingSource")
    org = relationship("Organization")
    commitments: Mapped[list["Commitment"]] = relationship(back_populates="budget_line")


class CommitmentStatus(str, enum.Enum):
    held = "held"             # reserved against the line (PO / call-off / approved plan earmark)
    invoiced = "invoiced"     # converted on invoice approval (Phase 5)
    paid = "paid"
    released = "released"     # cancelled / freed


class Commitment(IdMixin, TimestampMixin, Base):
    __tablename__ = "budget_commitments"

    budget_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("budget_lines.id"), index=True)
    source_entity: Mapped[str] = mapped_column(String(40))            # procurement_plan | purchase_order | …
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    source_ref: Mapped[str] = mapped_column(String(60), default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    status: Mapped[CommitmentStatus] = mapped_column(Enum(CommitmentStatus, native_enum=False, length=16),
                                                     default=CommitmentStatus.held, index=True)
    exception_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("budget_exceptions.id"), nullable=True)

    budget_line: Mapped[BudgetLine] = relationship(back_populates="commitments")


class ExceptionStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class BudgetException(IdMixin, TimestampMixin, Base):
    """FR-BUD-06: overruns need an approved exception with recorded justification."""
    __tablename__ = "budget_exceptions"

    budget_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("budget_lines.id"), index=True)
    source_entity: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_ref: Mapped[str] = mapped_column(String(60), default="")
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    shortfall: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    justification: Mapped[str] = mapped_column(Text)
    status: Mapped[ExceptionStatus] = mapped_column(Enum(ExceptionStatus, native_enum=False, length=16),
                                                    default=ExceptionStatus.pending)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    decision_note: Mapped[str] = mapped_column(Text, default="")

    budget_line = relationship("BudgetLine")
