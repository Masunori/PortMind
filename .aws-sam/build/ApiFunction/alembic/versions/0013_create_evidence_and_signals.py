"""Create normalized evidence and immutable canonical signal storage.

Revision ID: 0013
Revises: 0012
"""

from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("collection_batches", sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("collection_runs", sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("batch_id", sa.String(100)), sa.Column("source_id", sa.String(100)),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False), sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["collection_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="SET NULL"))
    op.create_table("evidence", sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False), sa.Column("collection_run_id", sa.String(100)),
        sa.Column("legacy_document_id", sa.String(100), unique=True), sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("title", sa.String(500), nullable=False), sa.Column("media_type", sa.String(200), nullable=False),
        sa.Column("content", sa.Text()), sa.Column("structured_content", sa.JSON()), sa.Column("content_reference", sa.String(2000)),
        sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("duplicate_of_id", sa.String(100)),
        sa.Column("source_url", sa.String(2000)), sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False), sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("processing_status", sa.String(30), nullable=False), sa.Column("parser_warnings", sa.JSON(), nullable=False),
        sa.Column("quality_metadata", sa.JSON(), nullable=False), sa.Column("retention_class", sa.String(30), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("raw_removed_at", sa.DateTime(timezone=True)), sa.Column("legal_hold", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["collection_run_id"], ["collection_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["legacy_document_id"], ["raw_documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["evidence.id"], ondelete="RESTRICT"))
    op.create_index("ix_evidence_content_hash", "evidence", ["content_hash"])
    op.create_table("evidence_assessments", sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("evidence_id", sa.String(100), nullable=False), sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("relevance_probability", sa.Float(), nullable=False), sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False), sa.Column("entity_hints", sa.JSON(), nullable=False),
        sa.Column("provider_metadata", sa.JSON(), nullable=False), sa.Column("context_version", sa.String(120), nullable=False),
        sa.Column("human_override", sa.String(30)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="CASCADE"))
    op.create_table("signals", sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("current_version_id", sa.String(120)), sa.Column("lifecycle_status", sa.String(30), nullable=False),
        sa.Column("review_status", sa.String(30), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("retention_class", sa.String(30), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("signal_versions", sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("signal_id", sa.String(100), nullable=False), sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("classification", sa.String(30), nullable=False), sa.Column("signal_type", sa.String(100), nullable=False),
        sa.Column("temporal_window", sa.JSON(), nullable=False), sa.Column("occurrence_probability", sa.Float(), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False), sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("grounding_confidence", sa.Float()), sa.Column("mapping_confidence", sa.Float()),
        sa.Column("provider_metadata", sa.JSON(), nullable=False), sa.Column("context_version", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("signal_id", "version", name="uq_signal_version"))
    op.create_table("signal_evidence", sa.Column("signal_version_id", sa.String(120), primary_key=True),
        sa.Column("evidence_id", sa.String(100), primary_key=True),
        sa.ForeignKeyConstraint(["signal_version_id"], ["signal_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="RESTRICT"))
    op.create_table("signal_entities", sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("signal_version_id", sa.String(120), nullable=False), sa.Column("mention", sa.String(300), nullable=False),
        sa.Column("entity_id", sa.String(100)), sa.Column("entity_type", sa.String(50)),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("method", sa.String(100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False), sa.Column("context_version", sa.String(120), nullable=False),
        sa.ForeignKeyConstraint(["signal_version_id"], ["signal_versions.id"], ondelete="CASCADE"))
    op.create_table("signal_effects", sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("signal_version_id", sa.String(120), nullable=False), sa.Column("mapping_proposal", sa.JSON(), nullable=False),
        sa.Column("local_validation", sa.JSON(), nullable=False), sa.Column("client_validation", sa.JSON(), nullable=False),
        sa.Column("normalized_disruption", sa.JSON()), sa.Column("catalog_version", sa.String(120), nullable=False),
        sa.Column("schema_hash", sa.String(64), nullable=False), sa.Column("context_version", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["signal_version_id"], ["signal_versions.id"], ondelete="CASCADE"))
    op.create_table("signal_relationships", sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("source_signal_version_id", sa.String(120), nullable=False),
        sa.Column("target_signal_version_id", sa.String(120), nullable=False),
        sa.Column("relationship", sa.String(40), nullable=False), sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_signal_version_id"], ["signal_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_signal_version_id"], ["signal_versions.id"], ondelete="CASCADE"))


def downgrade() -> None:
    for table in ("signal_relationships", "signal_effects", "signal_entities", "signal_evidence",
                  "signal_versions", "signals", "evidence_assessments"):
        op.drop_table(table)
    op.drop_index("ix_evidence_content_hash", table_name="evidence")
    op.drop_table("evidence"); op.drop_table("collection_runs"); op.drop_table("collection_batches")
