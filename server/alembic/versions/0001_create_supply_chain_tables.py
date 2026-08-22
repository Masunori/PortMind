"""Create supply-chain tables.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create nodes, edges, and shipments with their foreign keys."""

    op.create_table(
        "nodes",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("inventory", sa.Float(), nullable=False),
        sa.Column("capacity", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "edges",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("source_id", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=100), nullable=False),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("transit_time_hours", sa.Float(), nullable=False),
        sa.Column("cost", sa.Float(), nullable=False),
        sa.Column("capacity", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["target_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "shipments",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("origin_id", sa.String(length=100), nullable=False),
        sa.Column("destination_id", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("current_node_id", sa.String(length=100), nullable=False),
        sa.Column("route", sa.JSON(), nullable=False),
        sa.Column("expected_arrival", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["current_node_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["destination_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["origin_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop supply-chain tables in reverse dependency order."""

    op.drop_table("shipments")
    op.drop_table("edges")
    op.drop_table("nodes")
