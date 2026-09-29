"""Admin-managed public website content. Workflow: draft → in_review → published (→ archived)."""
import enum
import uuid
from datetime import datetime

from app.models.types import UTCDateTime
from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import IdMixin, TimestampMixin


class ContentStatus(str, enum.Enum):
    draft = "draft"
    in_review = "in_review"
    published = "published"
    archived = "archived"


class _Publishable:
    status: Mapped[ContentStatus] = mapped_column(Enum(ContentStatus, native_enum=False, length=16),
                                                  default=ContentStatus.draft, index=True)
    language: Mapped[str] = mapped_column(String(5), default="en")
    version: Mapped[int] = mapped_column(Integer, default=1)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")


class NewsPost(IdMixin, TimestampMixin, _Publishable, Base):
    __tablename__ = "cms_news"

    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40), default="Announcement")
    summary: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")      # Markdown
    cover_image: Mapped[str] = mapped_column(String(300), default="")
    cover_alt: Mapped[str] = mapped_column(String(200), default="")


class Page(IdMixin, TimestampMixin, _Publishable, Base):
    __tablename__ = "cms_pages"

    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)   # about, how-it-works, privacy, terms…
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")      # Markdown
    show_in_nav: Mapped[bool] = mapped_column(Boolean, default=False)


class FaqItem(IdMixin, TimestampMixin, Base):
    __tablename__ = "cms_faq"

    question: Mapped[str] = mapped_column(String(300))
    answer: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(5), default="en")
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)


class Resource(IdMixin, TimestampMixin, Base):
    __tablename__ = "cms_resources"

    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(300), default="")
    file_key: Mapped[str] = mapped_column(String(300), default="")
    file_name: Mapped[str] = mapped_column(String(200), default="")
    content_type: Mapped[str] = mapped_column(String(100), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    visibility: Mapped[str] = mapped_column(String(16), default="public")   # public | registered
    language: Mapped[str] = mapped_column(String(5), default="en")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True)


class SiteBlock(IdMixin, TimestampMixin, _Publishable, Base):
    """Structured homepage blocks, e.g. key='hero' {title, subtitle, cta_label}, key='stats' {show, items:[…]}."""
    __tablename__ = "cms_blocks"

    key: Mapped[str] = mapped_column(String(60), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)                 # working copy (draft)
    published_data: Mapped[dict] = mapped_column(JSON, default=dict)       # what the public sees


class ContentVersion(IdMixin, Base):
    __tablename__ = "cms_versions"

    entity: Mapped[str] = mapped_column(String(30), index=True)   # news | page | block
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class ContactMessage(IdMixin, TimestampMixin, Base):
    __tablename__ = "contact_messages"

    name: Mapped[str] = mapped_column(String(120))
    contact: Mapped[str] = mapped_column(String(120))
    topic: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="new")   # new | assigned | closed
    handled_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class MediaAsset(IdMixin, TimestampMixin, Base):
    """Images uploaded for the public website (section and page backgrounds). Served at /api/v1/public/media/{id}."""
    __tablename__ = "cms_media"

    title: Mapped[str] = mapped_column(String(200), default="")
    alt: Mapped[str] = mapped_column(String(300), default="")          # description for screen readers
    file_key: Mapped[str] = mapped_column(String(300))
    file_name: Mapped[str] = mapped_column(String(200), default="")
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
