"""Reusable approval engine (FR-PLT-01, SRS §7.1). Definitions live in app/services/workflow.py (versioned in code);
instances and every action are stored here, giving the approval history and SLA tracking."""
import enum
import uuid
from datetime import datetime

from app.models.types import UTCDateTime
from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import IdMixin


class InstanceStatus(str, enum.Enum):
    active = "active"
    approved = "approved"
    rejected = "rejected"
    returned = "returned"
    cancelled = "cancelled"


class WorkflowInstance(IdMixin, Base):
    __tablename__ = "workflow_instances"

    definition: Mapped[str] = mapped_column(String(60), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    entity: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    entity_ref: Mapped[str] = mapped_column(String(80), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    scope_org_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    amount: Mapped[float | None] = mapped_column(nullable=True)            # for threshold routing
    stage_index: Mapped[int] = mapped_column(Integer, default=0)
    stage_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[InstanceStatus] = mapped_column(Enum(InstanceStatus, native_enum=False, length=16),
                                                   default=InstanceStatus.active, index=True)
    initiator_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict)

    actions: Mapped[list["WorkflowAction"]] = relationship(back_populates="instance", cascade="all, delete-orphan",
                                                           order_by="WorkflowAction.at")


class WorkflowAction(IdMixin, Base):
    __tablename__ = "workflow_actions"

    instance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True)
    stage_index: Mapped[int] = mapped_column(Integer)
    stage_key: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(20))       # submit | approve | reject | return | escalate | cancel
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_label: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(UTCDateTime())

    instance: Mapped[WorkflowInstance] = relationship(back_populates="actions")
