"""Phase 4 — aggregation & quality, inventory, logistics & delivery (SRS §3.8–3.10), plus exception cases (§3.15)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from app.models.types import UTCDateTime
from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin

E16 = dict(native_enum=False, length=24)


class BatchStatus(str, enum.Enum):
    open = "open"                          # still receiving farmer intake
    awaiting_inspection = "awaiting_inspection"
    cleared = "cleared"                    # accepted (fully or partly) → can be stocked / dispatched
    rejected = "rejected"
    depleted = "depleted"
    recalled = "recalled"                  # withdrawn after a food-safety concern: blocked everywhere


class Batch(IdMixin, TimestampMixin, Base):
    __tablename__ = "batches"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)   # BATCH-2026-A-000145 (QR-ready)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)   # hub where formed
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    po_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("purchase_orders.id"), nullable=True, index=True)
    commodity_code: Mapped[str] = mapped_column(String(40))
    variety: Mapped[str] = mapped_column(String(80), default="")
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    intake_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    accepted_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    rejected_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    grade: Mapped[str] = mapped_column(String(20), default="")
    production_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[BatchStatus] = mapped_column(Enum(BatchStatus, **E16), default=BatchStatus.open, index=True)
    recalled_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    recall_reason: Mapped[str] = mapped_column(Text, default="", server_default="")

    intakes: Mapped[list["Intake"]] = relationship(back_populates="batch", order_by="Intake.received_at")
    location = relationship("Organization")


class Intake(IdMixin, TimestampMixin, Base):
    """Produce received from a farmer or producer group at an aggregation hub (FR-AGG-01)."""
    __tablename__ = "intakes"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batches.id"), index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    producer_name: Mapped[str] = mapped_column(String(160))
    producer_phone: Mapped[str] = mapped_column(String(20), default="")
    producer_group: Mapped[str] = mapped_column(String(160), default="")
    producer_gender: Mapped[str] = mapped_column(String(16), default="")     # for inclusion reporting
    producer_youth: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    commodity_code: Mapped[str] = mapped_column(String(40))
    variety: Mapped[str] = mapped_column(String(80), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    source_location: Mapped[str] = mapped_column(String(160), default="")
    received_at: Mapped[datetime] = mapped_column(UTCDateTime())
    client_ref: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)   # offline idempotency

    batch: Mapped[Batch] = relationship(back_populates="intakes")


class InspectionResult(str, enum.Enum):
    accepted = "accepted"
    partially_accepted = "partially_accepted"
    downgraded = "downgraded"
    rejected = "rejected"


class QualityInspection(IdMixin, TimestampMixin, Base):
    __tablename__ = "quality_inspections"

    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batches.id"), index=True)
    inspector_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    inspected_at: Mapped[datetime] = mapped_column(UTCDateTime())
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)      # {"moisture_pct": 12.8, …}
    checks: Mapped[list] = mapped_column(JSON, default=list)          # [{param, value, limit, pass}]
    grade: Mapped[str] = mapped_column(String(20), default="")
    result: Mapped[InspectionResult] = mapped_column(Enum(InspectionResult, **E16))
    accepted_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    rejected_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    reason: Mapped[str] = mapped_column(Text, default="")
    corrective_action: Mapped[str] = mapped_column(Text, default="")
    photos: Mapped[list] = mapped_column(JSON, default=list)          # storage keys
    captured_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    client_ref: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)


class MovementType(str, enum.Enum):
    receipt = "receipt"              # cleared batch into stock / school receipt
    issue = "issue"                  # out on dispatch
    transfer_in = "transfer_in"
    transfer_out = "transfer_out"
    adjustment = "adjustment"        # needs approval
    return_ = "return"
    waste = "waste"                  # damaged / expired, needs approval


class MovementStatus(str, enum.Enum):
    posted = "posted"
    pending_approval = "pending_approval"
    rejected = "rejected"


class StockMovement(IdMixin, TimestampMixin, Base):
    """Stock ledger (FR-INV-03). Balance = Σ posted quantity per location + batch."""
    __tablename__ = "stock_movements"

    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("batches.id"), nullable=True, index=True)
    commodity_code: Mapped[str] = mapped_column(String(40), index=True)
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))           # signed
    type: Mapped[MovementType] = mapped_column(Enum(MovementType, **E16))
    status: Mapped[MovementStatus] = mapped_column(Enum(MovementStatus, **E16), default=MovementStatus.posted, index=True)
    source_entity: Mapped[str] = mapped_column(String(40), default="")
    source_ref: Mapped[str] = mapped_column(String(60), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)     # e.g. {"meals_served": 600, "served_on": "2026-09-23"}


class StockCount(IdMixin, TimestampMixin, Base):
    """Physical count & reconciliation (FR-INV-06). Variances post as adjustments once approved."""
    __tablename__ = "stock_counts"

    reference: Mapped[str] = mapped_column(String(40), unique=True)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    lines: Mapped[list] = mapped_column(JSON, default=list)   # [{batch_id, commodity_code, system_qty, counted_qty, variance}]
    status: Mapped[str] = mapped_column(String(20), default="draft")   # draft | submitted | approved | rejected
    note: Mapped[str] = mapped_column(Text, default="")


class DispatchStatus(str, enum.Enum):
    planned = "planned"
    dispatched = "dispatched"
    in_transit = "in_transit"
    delivered = "delivered"          # all stops delivered by the driver
    closed = "closed"                # all stops confirmed by schools
    cancelled = "cancelled"


class Dispatch(IdMixin, TimestampMixin, Base):
    __tablename__ = "dispatches"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    po_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    source_location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    county_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    vehicle: Mapped[str] = mapped_column(String(40), default="")
    driver_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    driver_name: Mapped[str] = mapped_column(String(120), default="")
    driver_phone: Mapped[str] = mapped_column(String(20), default="")
    planned_date: Mapped[date] = mapped_column(Date)
    status: Mapped[DispatchStatus] = mapped_column(Enum(DispatchStatus, **E16), default=DispatchStatus.planned, index=True)
    milestones: Mapped[list] = mapped_column(JSON, default=list)   # [{status, at, by, note, lat, lng}]
    route: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # suggested stop order, distances (Phase 6)

    lines: Mapped[list["DispatchLine"]] = relationship(back_populates="dispatch", cascade="all, delete-orphan")
    source = relationship("Organization", foreign_keys=[source_location_id])


class DispatchLine(IdMixin, Base):
    __tablename__ = "dispatch_lines"

    dispatch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dispatches.id", ondelete="CASCADE"), index=True)
    po_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("po_lines.id"))
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    commodity_code: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    delivered_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)   # driver
    accepted_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)    # school
    rejected_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    rejection_reason: Mapped[str] = mapped_column(String(300), default="")

    dispatch: Mapped[Dispatch] = relationship(back_populates="lines")
    school = relationship("Organization", foreign_keys=[school_id])


class ProofOfDelivery(IdMixin, TimestampMixin, Base):
    """School confirmation (FR-LOG-04). One per dispatch stop (school). Offline-capable via client_ref."""
    __tablename__ = "proofs_of_delivery"

    dispatch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dispatches.id"), index=True)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    receiver_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    receiver_name: Mapped[str] = mapped_column(String(160))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime())
    condition: Mapped[str] = mapped_column(String(24), default="good")      # good | partial | rejected
    remarks: Mapped[str] = mapped_column(Text, default="")
    signature_key: Mapped[str] = mapped_column(String(300), default="")
    photos: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24))                         # accepted | partially_accepted | rejected
    captured_offline: Mapped[bool] = mapped_column(Boolean, default=False)
    client_ref: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)


class CaseStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class ExceptionCase(IdMixin, TimestampMixin, Base):
    """Operational exceptions raised automatically when rules are breached (FR-LOG-05, FR-AGG-04, FR-RSK-03)."""
    __tablename__ = "exception_cases"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)     # short_delivery | quality_rejection | damaged | late_delivery | stock_variance …
    severity: Mapped[str] = mapped_column(String(10), default="medium")   # high | medium | low
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    entity_ref: Mapped[str] = mapped_column(String(60), default="")
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True, index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    owner_role: Mapped[str] = mapped_column(String(60), default="")
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus, **E16), default=CaseStatus.open, index=True)
    corrective_action: Mapped[str] = mapped_column(Text, default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
