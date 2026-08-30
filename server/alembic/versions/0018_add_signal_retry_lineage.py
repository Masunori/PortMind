"""Add immutable lineage between retried signal candidates.

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("signals") as batch_op:
        batch_op.add_column(sa.Column("retry_of_signal_id", sa.String(100)))
        batch_op.create_foreign_key(
            "fk_signals_retry_of_signal_id", "signals",
            ["retry_of_signal_id"], ["id"], ondelete="RESTRICT",
        )
        batch_op.create_index(
            "ix_signals_retry_of_signal_id", ["retry_of_signal_id"])


def downgrade() -> None:
    with op.batch_alter_table("signals") as batch_op:
        batch_op.drop_index("ix_signals_retry_of_signal_id")
        batch_op.drop_constraint(
            "fk_signals_retry_of_signal_id", type_="foreignkey")
        batch_op.drop_column("retry_of_signal_id")
