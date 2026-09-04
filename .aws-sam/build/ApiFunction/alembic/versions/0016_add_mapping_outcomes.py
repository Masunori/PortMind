"""Persist signal processing state and explicit mapping outcomes.

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("signal_versions") as batch:
        batch.add_column(sa.Column("processing_state", sa.String(30), nullable=False,
                                   server_default="INTERPRETED"))
    with op.batch_alter_table("signal_effects") as batch:
        batch.add_column(sa.Column("outcome", sa.String(40), nullable=False,
                                   server_default="MAPPED"))
        batch.add_column(sa.Column("errors", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("signal_effects") as batch:
        batch.drop_column("errors")
        batch.drop_column("outcome")
    with op.batch_alter_table("signal_versions") as batch:
        batch.drop_column("processing_state")
