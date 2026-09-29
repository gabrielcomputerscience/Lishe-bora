"""Phase 5 — invoices with three-way match, payments (SRS §3.11), complaints & grievances (§3.12)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from app.models.types import UTCDateTime
from sqlalchemy import JSON, Boolean, Date, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin

E24 = dict(native_enum=False, length=24)


class InvoiceStatus(str, enum.Enum):
    submitted = "submitted"      # matched, waiting for finance verification
    verified = "verified"        # finance verified the match, waiting for approval
    approved = "approved"        # approved for payment
    partially_paid = "partially_paid"
    paid = "paid"
    returned = "returned"        # sent back to the supplier to correct
    rejected = "rejected"
    cancelled = "cancelled"


class Invoice(IdMixin, TimestampMixin, Base):
    __tablename__ = "invoices"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)          # INV-2026-00001
    supplier_invoice_no: Mapped[str] = mapped_column(String(60))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), index=True)
    po_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contracts.id"), index=True)
    county_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    invoice_date: Mapped[date] = mapped_column(Date)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus, **E24), default=InvoiceStatus.submitted, index=True)
    match: Mapped[dict] = mapped_column(JSON, default=dict)      # evidence: per line PO / received / invoiced, result
    document_key: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(UTCDateTime())
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    lines: Mapped[list["InvoiceLine"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    supplier = relationship("Supplier")
    po = relationship("PurchaseOrder")


class InvoiceLine(IdMixin, Base):
    __tablename__ = "invoice_lines"

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    po_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("po_lines.id"), index=True)
    commodity_code: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))

    invoice: Mapped[Invoice] = relationship(back_populates="lines")


class PaymentStatus(str, enum.Enum):
    completed = "completed"
    reversed = "reversed"


class Payment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)          # PAY-2026-00001
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    method: Mapped[str] = mapped_column(String(20))              # bank | mpesa | cheque | ifmis
    transaction_ref: Mapped[str] = mapped_column(String(80))
    paid_on: Mapped[date] = mapped_column(Date)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, **E24), default=PaymentStatus.completed)
    note: Mapped[str] = mapped_column(Text, default="")


class ComplaintStatus(str, enum.Enum):
    submitted = "submitted"
    investigating = "investigating"
    resolved = "resolved"
    closed = "closed"            # complainant confirmed or no response after resolution


class Complaint(IdMixin, TimestampMixin, Base):
    """Complaints and grievances from schools, suppliers, staff or the public (FR-CMP-01…04)."""
    __tablename__ = "complaints"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)          # CMP-2026-00001
    channel: Mapped[str] = mapped_column(String(16), default="portal")                   # portal | public | phone | sms
    category: Mapped[str] = mapped_column(String(40), index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    subject: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)     # county for routing
    school_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    entity: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    entity_ref: Mapped[str] = mapped_column(String(60), default="")
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    contact: Mapped[str] = mapped_column(String(120), default="")
    anonymous: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[ComplaintStatus] = mapped_column(Enum(ComplaintStatus, **E24), default=ComplaintStatus.submitted, index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    resolution: Mapped[str] = mapped_column(Text, default="")
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    satisfaction: Mapped[int | None] = mapped_column(Integer, nullable=True)                # 1–5 from the complainant
    history: Mapped[list] = mapped_column(JSON, default=list)                               # [{at, by, action, note}]
