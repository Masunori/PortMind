"""Add plan human-decision status.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add generated status to existing and future plans."""

    op.add_column(
        "plans",
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="GENERATED",
        ),
    )


def downgrade() -> None:
    """Remove plan human-decision status."""

    op.drop_column("plans", "status")
