"""Make automatic collection an explicit per-source choice.

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add scheduling disabled for all existing and future sources."""

    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.add_column(sa.Column(
            "schedule_enabled", sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ))
    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.alter_column("schedule_enabled", server_default=None)


def downgrade() -> None:
    """Return to inferring scheduling from general source enablement."""

    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.drop_column("schedule_enabled")
