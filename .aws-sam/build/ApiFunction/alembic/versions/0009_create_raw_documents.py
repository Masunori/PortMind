"""Create normalized raw documents.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create documents with source provenance and hash lookup."""

    op.create_table(
        "raw_documents",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("media_type", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_raw_documents_content_hash", "raw_documents", ["content_hash"])


def downgrade() -> None:
    """Remove normalized raw documents."""

    op.drop_index("ix_raw_documents_content_hash", table_name="raw_documents")
    op.drop_table("raw_documents")
