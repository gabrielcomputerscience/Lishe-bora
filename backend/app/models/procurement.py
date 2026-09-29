"""e-Procurement (SRS §3.6–3.7): sourcing events, lots, sealed bids, clarifications, evaluation, awards,
contracts and purchase orders."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from app.models.types import UTCDateTime
from sqlalchemy import (JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class ProcurementMethod(str, enum.Enum):
    rfq = "rfq"
    competitive = "competitive"
    framework = "framework"
    call_off = "call_off"
    direct = "direct"


class EventStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    published = "published"
    open = "open"
    closed = "closed"
    under_evaluation = "under_evaluation"
    evaluated = "evaluated"
    approved = "approved"          # award in approval
    awarded = "awarded"
    cancelled = "cancelled"


DEFAULT_CRITERIA = [   # SRS §3.6 illustrative weights — configurable per event
    {"key": "technical", "label": "Technical compliance", "max": 20, "auto": False},
    {"key": "capacity", "label": "Capacity to supply", "max": 15, "auto": False},
    {"key": "quality", "label": "Quality & food safety", "max": 10, "auto": False},
    {"key": "local", "label": "Local sourcing / distance", "max": 10, "auto": False},
    {"key": "inclusion", "label": "Inclusion (verified women/youth/PWD-led)", "max": 5, "auto": True},
]


class ProcurementEvent(IdMixin, TimestampMixin, Base):
    __tablename__ = "procurement_events"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    method: Mapped[ProcurementMethod] = mapped_column(Enum(ProcurementMethod, native_enum=False, length=16))
    county_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("procurement_plans.id"), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    eligibility: Mapped[str] = mapped_column(String(200), default="")
    categories: Mapped[list] = mapped_column(JSON, default=list)          # non-empty ⇒ restricted to prequalified categories
    estimated_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    opens_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    closes_at: Mapped[datetime] = mapped_column(UTCDateTime())
    clarification_deadline: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus, native_enum=False, length=20), default=EventStatus.draft)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    technical_weight: Mapped[int] = mapped_column(Integer, default=60)
    financial_weight: Mapped[int] = mapped_column(Integer, default=40)
    criteria: Mapped[list] = mapped_column(JSON, default=lambda: [dict(c) for c in DEFAULT_CRITERIA])
    required_docs: Mapped[list] = mapped_column(JSON, default=lambda: ["registration", "bank"])
    contract_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    opened_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    results: Mapped[dict] = mapped_column(JSON, default=dict)             # consolidated evaluation
    awarded_to: Mapped[str] = mapped_column(String(300), default="")      # public summary
    awarded_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    awarded_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    county = relationship("Organization")
    lots: Mapped[list["ProcurementLot"]] = relationship(back_populates="event", cascade="all, delete-orphan",
                                                        order_by="ProcurementLot.lot_no")


class ProcurementLot(IdMixin, Base):
    __tablename__ = "procurement_lots"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_events.id", ondelete="CASCADE"), index=True)
    lot_no: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160))
    commodity_code: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(60), default="")
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    specification: Mapped[str] = mapped_column(Text, default="")
    delivery_window: Mapped[str] = mapped_column(String(160), default="")
    schools: Mapped[list] = mapped_column(JSON, default=list)
    plan_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    estimated_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    event: Mapped[ProcurementEvent] = relationship(back_populates="lots")


class BidStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    withdrawn = "withdrawn"
    opened = "opened"
    awarded = "awarded"
    unsuccessful = "unsuccessful"


class Bid(IdMixin, TimestampMixin, Base):
    """Bid contents are sealed (encrypted) until the event closes and is formally opened (FR-PRO-05)."""
    __tablename__ = "bids"
    __table_args__ = (UniqueConstraint("event_id", "supplier_id", name="uq_bid_supplier_event"),)

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_events.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), index=True)
    status: Mapped[BidStatus] = mapped_column(Enum(BidStatus, native_enum=False, length=16), default=BidStatus.draft)
    sealed_payload: Mapped[str] = mapped_column(Text, default="")        # Fernet token
    payload_sha256: Mapped[str] = mapped_column(String(64), default="")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    opened_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # decrypted copy after opening
    lots_bid: Mapped[int] = mapped_column(Integer, default=0)                 # non-sensitive metadata

    supplier = relationship("Supplier")


class Clarification(IdMixin, TimestampMixin, Base):
    __tablename__ = "clarifications"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_events.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), default="question")   # question | amendment | award_query
    question: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    answered_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class EvaluationAssignment(IdMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_assignments"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_eval_user"),)

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    coi_declared_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    has_conflict: Mapped[bool] = mapped_column(Boolean, default=False)
    coi_statement: Mapped[str] = mapped_column(Text, default="")
    scores: Mapped[dict] = mapped_column(JSON, default=dict)     # {bid_id: {criterion_key: number, "_comment": str}}
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    user = relationship("User")


class AwardStatus(str, enum.Enum):
    proposed = "proposed"
    approved = "approved"
    cancelled = "cancelled"


class Award(IdMixin, TimestampMixin, Base):
    __tablename__ = "awards"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_events.id", ondelete="CASCADE"), index=True)
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_lots.id"))
    bid_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bids.id"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    value: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    status: Mapped[AwardStatus] = mapped_column(Enum(AwardStatus, native_enum=False, length=16), default=AwardStatus.proposed)

    lot = relationship("ProcurementLot")
    supplier = relationship("Supplier")


class ContractKind(str, enum.Enum):
    purchase = "purchase"     # one-off: a single PO for the full quantity
    framework = "framework"   # call-off orders drawn against the balance


class ContractStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    expired = "expired"
    terminated = "terminated"


class Contract(IdMixin, TimestampMixin, Base):
    __tablename__ = "contracts"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_events.id"), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), index=True)
    county_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    budget_line_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("budget_lines.id"), nullable=True)
    kind: Mapped[ContractKind] = mapped_column(Enum(ContractKind, native_enum=False, length=16))
    value: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    status: Mapped[ContractStatus] = mapped_column(Enum(ContractStatus, native_enum=False, length=16),
                                                   default=ContractStatus.active)
    terms: Mapped[str] = mapped_column(Text, default="")

    supplier = relationship("Supplier")
    lines: Mapped[list["ContractLine"]] = relationship(back_populates="contract", cascade="all, delete-orphan")


class ContractLine(IdMixin, Base):
    __tablename__ = "contract_lines"

    contract_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"), index=True)
    lot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_lots.id"))
    commodity_code: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity_ordered: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)

    contract: Mapped[Contract] = relationship(back_populates="lines")
    lot = relationship("ProcurementLot")

    @property
    def remaining(self) -> Decimal:
        return Decimal(self.quantity) - Decimal(self.quantity_ordered or 0)


class POStatus(str, enum.Enum):
    issued = "issued"
    acknowledged = "acknowledged"
    partially_fulfilled = "partially_fulfilled"
    fulfilled = "fulfilled"
    cancelled = "cancelled"


class PurchaseOrder(IdMixin, TimestampMixin, Base):
    __tablename__ = "purchase_orders"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    contract_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contracts.id"), index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"), index=True)
    county_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    status: Mapped[POStatus] = mapped_column(Enum(POStatus, native_enum=False, length=24), default=POStatus.issued)
    total: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    delivery_window: Mapped[str] = mapped_column(String(160), default="")
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime())
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    supplier = relationship("Supplier")
    contract = relationship("Contract")
    lines: Mapped[list["POLine"]] = relationship(back_populates="po", cascade="all, delete-orphan")


class POLine(IdMixin, Base):
    __tablename__ = "po_lines"

    po_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True)
    contract_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("contract_lines.id"))
    commodity_code: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    schools: Mapped[list] = mapped_column(JSON, default=list)
    dispatched_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    accepted_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0")
    rejected_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, server_default="0")

    po: Mapped[PurchaseOrder] = relationship(back_populates="lines")
