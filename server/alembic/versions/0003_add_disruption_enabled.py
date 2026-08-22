"""Add disruption enabled state.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add an enabled flag and activate all existing disruptions."""

    op.add_column(
        "disruptions",
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    """Remove the disruption enabled flag."""

    op.drop_column("disruptions", "enabled")
