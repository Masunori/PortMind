"""Create scenarios table.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the scenarios table with inline disruption JSON."""

    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("disruptions", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop the scenarios table."""

    op.drop_table("scenarios")
