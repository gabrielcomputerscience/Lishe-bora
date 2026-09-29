"""Website images (section and page backgrounds)

Revision ID: 0008_cms_media
Revises: 3ff9af448460
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_cms_media"
down_revision: Union[str, Sequence[str], None] = "3ff9af448460"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("cms_media",
                    sa.Column("title", sa.String(length=200), nullable=False),
                    sa.Column("alt", sa.String(length=300), nullable=False),
                    sa.Column("file_key", sa.String(length=300), nullable=False),
                    sa.Column("file_name", sa.String(length=200), nullable=False),
                    sa.Column("content_type", sa.String(length=100), nullable=False),
                    sa.Column("size_bytes", sa.Integer(), nullable=False),
                    sa.Column("id", sa.Uuid(), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("created_by", sa.Uuid(), nullable=True),
                    sa.Column("updated_by", sa.Uuid(), nullable=True),
                    sa.PrimaryKeyConstraint("id"))


def downgrade() -> None:
    op.drop_table("cms_media")
