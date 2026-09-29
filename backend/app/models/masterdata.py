from decimal import Decimal

from sqlalchemy import JSON, Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class Commodity(IdMixin, TimestampMixin, Base):
    __tablename__ = "commodities"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), index=True)       # cereals, pulses, vegetables…
    unit: Mapped[str] = mapped_column(String(16), default="kg")
    standard_pack: Mapped[str] = mapped_column(String(60), default="")
    food_group: Mapped[str] = mapped_column(String(60), default="")
    quality_spec: Mapped[dict] = mapped_column(JSON, default=dict)     # e.g. {"max_moisture_pct": 13.5}
    default_portion_g: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # KES per unit, for estimates
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SystemSetting(IdMixin, TimestampMixin, Base):
    """Configurable parameters (thresholds, SLAs…) editable without code changes (FR-MD-04, FR-PLT-05)."""
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str] = mapped_column(String(300), default="")
