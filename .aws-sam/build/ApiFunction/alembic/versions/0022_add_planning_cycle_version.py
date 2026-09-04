"""add optimistic version to planning cycles

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa
revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("planning_cycles", sa.Column("version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("signals", sa.Column("revision", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("source_collection_leases",
        sa.Column("source_id",sa.String(length=100),nullable=False),
        sa.Column("owner",sa.String(length=120),nullable=False),
        sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["source_id"],["data_sources.id"],ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_id"))

def downgrade() -> None:
    op.drop_table("source_collection_leases")
    op.drop_column("signals", "revision")
    op.drop_column("planning_cycles", "version")
