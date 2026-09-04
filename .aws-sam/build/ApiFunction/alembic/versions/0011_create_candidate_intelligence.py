"""Create grounded candidate, event, alias, and history tables.

Revision ID: 0011
Revises: 0010
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the complete pre-confirmation intelligence data model."""

    op.create_table(
        "entity_aliases",
        sa.Column("alias", sa.String(length=300), primary_key=True),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "intelligence_events",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("disruption_type", sa.String(length=50), nullable=False),
        sa.Column("affected_entity_ids", sa.JSON(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "event_documents",
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("document_id", sa.String(length=100), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["intelligence_events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["raw_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id", "document_id"),
    )
    op.create_table(
        "disruption_candidates",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column("document_id", sa.String(length=100), nullable=False),
        sa.Column("event_id", sa.String(length=100), nullable=True),
        sa.Column("disruption_type", sa.String(length=50), nullable=False),
        sa.Column("affected_locations", sa.JSON(), nullable=False),
        sa.Column("affected_node_ids", sa.JSON(), nullable=False),
        sa.Column("affected_edge_ids", sa.JSON(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False),
        sa.Column("effects_json", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("validation_status", sa.String(length=30), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("review_status", sa.String(length=30), nullable=False),
        sa.Column("confirmed_disruption_id", sa.String(length=100), nullable=True),
        sa.Column("run_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["raw_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["intelligence_events.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["confirmed_disruption_id"], ["disruptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "candidate_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("candidate_id", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["disruption_candidates.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("candidate_id", "version", name="uq_candidate_version"),
    )


def downgrade() -> None:
    """Remove pre-confirmation intelligence tables in dependency order."""

    op.drop_table("candidate_versions")
    op.drop_table("disruption_candidates")
    op.drop_table("event_documents")
    op.drop_table("intelligence_events")
    op.drop_table("entity_aliases")
