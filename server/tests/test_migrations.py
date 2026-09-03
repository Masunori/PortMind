"""Integration tests for the Alembic migration chain."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migrations_produce_only_platform_owned_tables(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A fresh database contains only final platform-owned tables."""

    database_path = tmp_path / "migration.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "plans",
        "scenarios",
        "data_sources",
        "collection_batches",
        "collection_runs",
        "evidence",
        "evidence_assessments",
        "signals",
        "signal_versions",
        "signal_evidence",
        "signal_entities",
        "signal_effects",
        "signal_relationships",
        "experiment_packages",
        "simulation_result_copies",
        "planning_cycles",
        "agent_prompts",
    }
    assert "legacy_document_id" not in {
        column["name"] for column in inspect(engine).get_columns("evidence")
    }
    assert "retry_of_signal_id" in {
        column["name"] for column in inspect(engine).get_columns("signals")
    }
    assert "is_target" in {
        column["name"] for column in inspect(engine).get_columns("signal_entities")
    }
    assert "schedule_enabled" in {
        column["name"] for column in inspect(engine).get_columns("data_sources")
    }
    engine.dispose()
