"""Create versioned schemas, attributes, rules, and context state.

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add safe typed extension infrastructure without changing core fields."""

    op.create_table(
        "entity_schemas",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("entity_kind", sa.String(20), nullable=False),
        sa.Column("current_version_id", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "schema_versions",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("schema_id", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["schema_id"], ["entity_schemas.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("schema_id", "version", name="uq_schema_version"),
    )
    with op.batch_alter_table("nodes") as batch:
        batch.add_column(sa.Column("schema_version_id", sa.String(120), nullable=True))
        batch.add_column(sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.create_foreign_key("fk_nodes_schema_version", "schema_versions", ["schema_version_id"], ["id"], ondelete="RESTRICT")
    with op.batch_alter_table("edges") as batch:
        batch.add_column(sa.Column("schema_version_id", sa.String(120), nullable=True))
        batch.add_column(sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.create_foreign_key("fk_edges_schema_version", "schema_versions", ["schema_version_id"], ["id"], ondelete="RESTRICT")
    op.create_table(
        "simulation_rules",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("trigger", sa.String(40), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("source", sa.String(200), nullable=False),
        sa.Column("target_metric", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "network_context_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Remove extension infrastructure in dependency order."""

    op.drop_table("network_context_state")
    op.drop_table("simulation_rules")
    with op.batch_alter_table("edges") as batch:
        batch.drop_constraint("fk_edges_schema_version", type_="foreignkey")
        batch.drop_column("attributes")
        batch.drop_column("schema_version_id")
    with op.batch_alter_table("nodes") as batch:
        batch.drop_constraint("fk_nodes_schema_version", type_="foreignkey")
        batch.drop_column("attributes")
        batch.drop_column("schema_version_id")
    op.drop_table("schema_versions")
    op.drop_table("entity_schemas")
