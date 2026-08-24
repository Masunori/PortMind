"""Create document relevance assessments.

Revision ID: 0010
Revises: 0009
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create provider assessments with explicit human overrides."""

    op.create_table(
        "document_assessments",
        sa.Column("document_id", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("relevance_probability", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("matched_entities", sa.JSON(), nullable=False),
        sa.Column("human_override", sa.String(length=30), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["raw_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id"),
    )


def downgrade() -> None:
    """Remove document assessments."""

    op.drop_table("document_assessments")
