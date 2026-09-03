"""Shared domain and isolated-database fixtures for backend tests."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services import evidence_service
from app.services import experiment_service
from app.services import source_service
from app.services import scheduler_service
from app.services import signal_service
from app.services import planning_service
from app.services import prompt_service


@pytest.fixture(autouse=True)
def deterministic_provider_environment(monkeypatch: pytest.MonkeyPatch):
    """Prevent developer cloud settings from leaking into deterministic tests."""

    for name in (
        "FILTER_PROVIDER",
        "INTERPRETER_PROVIDER",
        "HYPOTHESIS_PROVIDER",
        "RISK_PROVIDER",
        "PLANNER_PROVIDER",
        "BEDROCK_MODEL_ID",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def test_session_factory(monkeypatch: pytest.MonkeyPatch):
    """Replace application sessions with an isolated in-memory database."""

    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    monkeypatch.setattr(evidence_service, "SessionLocal", factory)
    monkeypatch.setattr(experiment_service, "SessionLocal", factory)
    monkeypatch.setattr(signal_service, "SessionLocal", factory)
    monkeypatch.setattr(planning_service, "SessionLocal", factory)
    monkeypatch.setattr(prompt_service, "SessionLocal", factory)
    monkeypatch.setattr(source_service, "SessionLocal", factory)
    monkeypatch.setattr(scheduler_service, "get_due_sources", source_service.get_due_sources)
    monkeypatch.setattr(scheduler_service, "record_source_run", source_service.record_source_run)

    yield factory

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        Base.metadata.drop_all(connection)
    engine.dispose()
