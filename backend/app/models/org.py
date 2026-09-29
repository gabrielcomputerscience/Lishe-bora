"""Organisations form one hierarchy used for data scope:
country > county > sub_county > ward/school_cluster > school, plus hubs, warehouses, suppliers and partners."""
import enum
import uuid

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class OrgType(str, enum.Enum):
    country = "country"
    county = "county"
    sub_county = "sub_county"
    ward = "ward"
    school_cluster = "school_cluster"
    school = "school"
    aggregation_centre = "aggregation_centre"
    warehouse = "warehouse"
    supplier = "supplier"
    partner = "partner"
    programme = "programme"


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    type: Mapped[OrgType] = mapped_column(Enum(OrgType, native_enum=False, length=32), index=True)
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # gps, enrolment, storage capacity, contacts…

    parent: Mapped["Organization | None"] = relationship(remote_side="Organization.id", back_populates="children")
    children: Mapped[list["Organization"]] = relationship(back_populates="parent")
