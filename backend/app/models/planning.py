"""Phase 2 — terms, menus, school demand, procurement plans (SRS §3.3, FR-DEM-01…07)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from app.models.types import UTCDateTime
from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class AcademicTerm(IdMixin, TimestampMixin, Base):
    __tablename__ = "academic_terms"
    __table_args__ = (UniqueConstraint("year", "term_no", name="uq_term"),)

    year: Mapped[int] = mapped_column(Integer)
    term_no: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(60))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    feeding_days: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(default=True)


class MenuStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    retired = "retired"


class Menu(IdMixin, TimestampMixin, Base):
    """A menu cycle (typically 5 school days). org_id NULL = programme-wide template."""
    __tablename__ = "menus"

    name: Mapped[str] = mapped_column(String(120))
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[MenuStatus] = mapped_column(Enum(MenuStatus, native_enum=False, length=16), default=MenuStatus.draft)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    days: Mapped[list["MenuDay"]] = relationship(back_populates="menu", cascade="all, delete-orphan",
                                                 order_by="MenuDay.day_index")


class MenuDay(IdMixin, Base):
    __tablename__ = "menu_days"

    menu_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menus.id", ondelete="CASCADE"), index=True)
    day_index: Mapped[int] = mapped_column(Integer)           # 1..n within the cycle
    label: Mapped[str] = mapped_column(String(40))            # "Mon"
    dish: Mapped[str] = mapped_column(String(200))            # "Githeri with cabbage"
    # [{"commodity": "MZE-G1", "portion_g": 150}, …]  grams per learner per meal
    components: Mapped[list] = mapped_column(JSON, default=list)

    menu: Mapped[Menu] = relationship(back_populates="days")


class DemandStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    validated = "validated"
    approved = "approved"
    returned = "returned"
    converted = "converted"      # consolidated into a procurement plan
    closed = "closed"


class SchoolDemand(IdMixin, TimestampMixin, Base):
    __tablename__ = "school_demands"
    __table_args__ = (UniqueConstraint("school_id", "term_id", name="uq_demand_school_term"),)

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    school_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    county_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=True)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_terms.id"), index=True)
    menu_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("menus.id"), nullable=True)
    enrolment: Mapped[int] = mapped_column(Integer, default=0)
    attendance_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("95"))
    feeding_days: Mapped[int] = mapped_column(Integer, default=0)
    wastage_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("3"))
    storage_capacity_kg: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    preferred_delivery: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    flags: Mapped[list] = mapped_column(JSON, default=list)       # validation findings [{code, severity, message}]
    nutrition: Mapped[dict] = mapped_column(JSON, default=dict)   # diversity summary
    status: Mapped[DemandStatus] = mapped_column(Enum(DemandStatus, native_enum=False, length=16),
                                                 default=DemandStatus.draft, index=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("procurement_plans.id"), nullable=True)

    lines: Mapped[list["DemandLine"]] = relationship(back_populates="demand", cascade="all, delete-orphan")
    school = relationship("Organization", foreign_keys=[school_id])
    term = relationship("AcademicTerm")
    menu = relationship("Menu")


class DemandLine(IdMixin, Base):
    __tablename__ = "demand_lines"

    demand_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("school_demands.id", ondelete="CASCADE"), index=True)
    commodity_code: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    grams_per_learner_cycle: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    gross_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    stock_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    net_qty: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    override_qty: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    override_reason: Mapped[str] = mapped_column(String(300), default="")

    demand: Mapped[SchoolDemand] = relationship(back_populates="lines")

    @property
    def final_qty(self) -> Decimal:
        return self.override_qty if self.override_qty is not None else self.net_qty


class PlanStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"        # in approval workflow (budget check → approval)
    approved = "approved"
    returned = "returned"
    rejected = "rejected"
    sourcing = "sourcing"          # converted into sourcing events (Phase 3)
    closed = "closed"


class ProcurementPlan(IdMixin, TimestampMixin, Base):
    __tablename__ = "procurement_plans"

    reference: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    county_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    term_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("academic_terms.id"))
    budget_line_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("budget_lines.id"), nullable=True)
    method: Mapped[str] = mapped_column(String(16), default="rfq")
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus, native_enum=False, length=16), default=PlanStatus.draft,
                                               index=True)
    notes: Mapped[str] = mapped_column(Text, default="")

    lines: Mapped[list["PlanLine"]] = relationship(back_populates="plan", cascade="all, delete-orphan",
                                                   order_by="PlanLine.lot")
    county = relationship("Organization")
    term = relationship("AcademicTerm")
    budget_line = relationship("BudgetLine")

    @property
    def estimated_value(self) -> Decimal:
        return sum((ln.estimated_value or Decimal(0) for ln in self.lines), Decimal(0))


class PlanLine(IdMixin, Base):
    __tablename__ = "plan_lines"

    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procurement_plans.id", ondelete="CASCADE"), index=True)
    lot: Mapped[str] = mapped_column(String(80))                    # e.g. "Cluster 1 · cereals"
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    commodity_code: Mapped[str] = mapped_column(String(40))
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    schools: Mapped[list] = mapped_column(JSON, default=list)       # [{school_id, name, qty}]
    delivery_window: Mapped[str] = mapped_column(String(120), default="")

    plan: Mapped[ProcurementPlan] = relationship(back_populates="lines")

    @property
    def estimated_value(self) -> Decimal | None:
        return None if self.unit_price is None else (self.quantity * self.unit_price).quantize(Decimal("0.01"))
