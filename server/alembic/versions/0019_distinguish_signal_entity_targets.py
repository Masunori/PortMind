"""Distinguish mentioned entities from disruption targets.

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Historical rows represented both mentions and targets, so preserve their
    # former operational meaning rather than attempting an unreliable backfill.
    with op.batch_alter_table("signal_entities") as batch_op:
        batch_op.add_column(sa.Column(
            "is_target", sa.Boolean(), nullable=False,
            server_default=sa.true(),
        ))
    with op.batch_alter_table("signal_entities") as batch_op:
        batch_op.alter_column("is_target", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("signal_entities") as batch_op:
        batch_op.drop_column("is_target")
