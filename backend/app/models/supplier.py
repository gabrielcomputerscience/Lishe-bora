import enum
import uuid
from datetime import date, datetime

from app.models.types import UTCDateTime
from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class SupplierType(str, enum.Enum):
    farmer = "farmer"
    farmer_group = "farmer_group"
    cooperative = "cooperative"
    aggregator = "aggregator"
    trader = "trader"
    processor = "processor"
    msme = "msme"


class SupplierStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    approved = "approved"
    prequalified = "prequalified"
    active = "active"
    suspended = "suspended"
    expired = "expired"
    rejected = "rejected"


# allowed transitions (FR-SUP-09); enforced in services.supplier
SUPPLIER_TRANSITIONS: dict[SupplierStatus, set[SupplierStatus]] = {
    SupplierStatus.draft: {SupplierStatus.submitted},
    SupplierStatus.submitted: {SupplierStatus.under_review, SupplierStatus.rejected},
    SupplierStatus.under_review: {SupplierStatus.approved, SupplierStatus.rejected, SupplierStatus.submitted},
    SupplierStatus.approved: {SupplierStatus.prequalified, SupplierStatus.rejected},
    SupplierStatus.prequalified: {SupplierStatus.active, SupplierStatus.suspended, SupplierStatus.expired},
    SupplierStatus.active: {SupplierStatus.suspended, SupplierStatus.expired},
    SupplierStatus.suspended: {SupplierStatus.active, SupplierStatus.expired},
    SupplierStatus.expired: {SupplierStatus.under_review},
    SupplierStatus.rejected: {SupplierStatus.submitted},
}


class Supplier(IdMixin, TimestampMixin, Base):
    __tablename__ = "suppliers"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), unique=True)
    county_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=True)
    supplier_type: Mapped[SupplierType] = mapped_column(Enum(SupplierType, native_enum=False, length=32))
    legal_name: Mapped[str] = mapped_column(String(200))
    registration_no: Mapped[str] = mapped_column(String(80), default="")
    kra_pin: Mapped[str] = mapped_column(String(20), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    sub_county: Mapped[str] = mapped_column(String(120), default="")
    commodities: Mapped[list] = mapped_column(JSON, default=list)            # commodity codes offered
    approved_categories: Mapped[list] = mapped_column(JSON, default=list)    # set at prequalification
    capacity: Mapped[dict] = mapped_column(JSON, default=dict)               # storage, transport, volumes
    members_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sms_language: Mapped[str] = mapped_column(String(5), default="en")
    # inclusion (FR-SUP-03): claimed by supplier, verified by an officer (BR-014)
    inclusion_claim: Mapped[dict] = mapped_column(JSON, default=dict)        # {"leadership": "women", "pct_women": 61, …}
    inclusion_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    inclusion_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    inclusion_verified_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    inclusion_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    assisted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)   # assisted registration
    status: Mapped[SupplierStatus] = mapped_column(Enum(SupplierStatus, native_enum=False, length=32),
                                                   default=SupplierStatus.draft, index=True)
    status_note: Mapped[str] = mapped_column(Text, default="")
    # Payment details (Phase 6). Changes stay "pending" until finance verifies them, then become "active".
    payment_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payment_details_pending: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prequalified_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    organization = relationship("Organization", foreign_keys=[organization_id])
    county = relationship("Organization", foreign_keys=[county_id])
    documents: Mapped[list["SupplierDocument"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    verified = "verified"
    rejected = "rejected"
    expired = "expired"


class SupplierDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "supplier_documents"

    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[str] = mapped_column(String(60))      # registration, kra_pin, food_safety, member_list, bank…
    version: Mapped[int] = mapped_column(Integer, default=1)
    file_key: Mapped[str] = mapped_column(String(300))
    file_name: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus, native_enum=False, length=16),
                                                   default=DocumentStatus.uploaded)
    review_note: Mapped[str] = mapped_column(Text, default="")

    supplier: Mapped[Supplier] = relationship(back_populates="documents")
