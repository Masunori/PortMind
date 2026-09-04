"""Create planning workflow snapshots.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("planning_cycles",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("planning_cycles")
