"""Integration tests for the Alembic migration chain."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_initial_migration_upgrades_and_downgrades(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The initial migration creates and cleanly removes every table."""

    database_path = tmp_path / "migration.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "nodes",
        "plans",
        "run_events",
        "runs",
        "edges",
        "shipments",
        "disruptions",
        "scenarios",
        "data_sources",
        "raw_documents",
        "document_assessments",
        "entity_aliases",
        "intelligence_events",
        "event_documents",
        "disruption_candidates",
        "candidate_versions",
        "entity_schemas",
        "schema_versions",
        "simulation_rules",
        "network_context_state",
    }
    disruption_columns = {
        column["name"]
        for column in inspect(engine).get_columns("disruptions")
    }
    assert "enabled" in disruption_columns
    plan_columns = {
        column["name"] for column in inspect(engine).get_columns("plans")
    }
    assert "status" in plan_columns
    node_columns = {column["name"] for column in inspect(engine).get_columns("nodes")}
    edge_columns = {column["name"] for column in inspect(engine).get_columns("edges")}
    assert {"schema_version_id", "attributes"} <= node_columns
    assert {"schema_version_id", "attributes"} <= edge_columns

    command.downgrade(config, "base")

    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    engine.dispose()
