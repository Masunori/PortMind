"""Create disruptions table.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the disruptions table and its JSON effect columns."""

    op.create_table(
        "disruptions",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("affected_node_ids", sa.JSON(), nullable=False),
        sa.Column("affected_edge_ids", sa.JSON(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("effects", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop the disruptions table."""

    op.drop_table("disruptions")
