"""Remove disposable client-owned and legacy workflow storage.

Revision ID: 0015
Revises: 0014
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("evidence") as batch:
        batch.drop_column("legacy_document_id")

    for table in (
        "candidate_versions", "disruption_candidates", "event_documents",
        "intelligence_events", "entity_aliases", "document_assessments",
        "raw_documents", "run_events", "runs", "disruptions", "shipments",
        "edges", "nodes", "network_context_state", "simulation_rules",
        "schema_versions", "entity_schemas",
    ):
        op.drop_table(table)


def downgrade() -> None:
    raise RuntimeError(
        "0015 is intentionally irreversible because removed client and legacy data is disposable"
    )
