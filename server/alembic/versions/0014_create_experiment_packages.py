"""Create immutable experiment packages and normalized result copies.

Revision ID: 0014
Revises: 0013
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("experiment_packages", sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("context_version", sa.String(120), nullable=False),
        sa.Column("state_version", sa.String(120), nullable=False), sa.Column("signal_version_ids", sa.JSON(), nullable=False),
        sa.Column("disruptions", sa.JSON(), nullable=False), sa.Column("occurrence_probability", sa.Float(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False), sa.Column("validation_summary", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("client_run_id", sa.String(120)), sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("simulation_result_copies", sa.Column("run_id", sa.String(120), primary_key=True),
        sa.Column("experiment_id", sa.String(120), nullable=False), sa.Column("context_version", sa.String(120), nullable=False),
        sa.Column("state_version", sa.String(120), nullable=False), sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiment_packages.id"], ondelete="RESTRICT"))


def downgrade() -> None:
    op.drop_table("simulation_result_copies")
    op.drop_table("experiment_packages")
