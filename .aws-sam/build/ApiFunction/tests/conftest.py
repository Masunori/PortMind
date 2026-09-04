"""Shared domain and isolated-database fixtures for backend tests."""

import os
from uuid import uuid4

import boto3
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
from app.repositories.postgres import plan as plan_repository
from app.repositories.postgres import planning as planning_repository
from app.repositories.postgres import evidence as evidence_repository
from app.repositories.postgres import experiment as experiment_repository
from app.repositories.postgres import prompt as prompt_repository
from app.repositories.postgres import scenario as scenario_repository
from app.repositories.postgres import source as source_repository
from app.repositories.postgres import signal as signal_repository
from app.repositories.postgres import (PostgresEvidenceRepository, PostgresExperimentRepository,
    PostgresPlanRepository, PostgresPlanningCycleRepository, PostgresPromptRepository,
    PostgresScenarioRepository, PostgresSignalRepository, PostgresSourceRepository)


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

    monkeypatch.setattr(evidence_repository, "SessionLocal", factory)
    monkeypatch.setattr(experiment_repository, "SessionLocal", factory)
    monkeypatch.setattr(signal_repository, "SessionLocal", factory)
    monkeypatch.setattr(planning_repository, "SessionLocal", factory)
    monkeypatch.setattr(prompt_repository, "SessionLocal", factory)
    monkeypatch.setattr(source_repository, "SessionLocal", factory)
    monkeypatch.setattr(plan_repository, "SessionLocal", factory)
    monkeypatch.setattr(scenario_repository, "SessionLocal", factory)
    monkeypatch.setattr(scheduler_service, "get_due_sources", source_service.get_due_sources)
    monkeypatch.setattr(scheduler_service, "record_source_run", source_service.record_source_run)

    yield factory

    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        Base.metadata.drop_all(connection)
    engine.dispose()


@pytest.fixture(params=("postgres", "dynamodb"), ids=("postgres", "dynamodb"))
def repository_factories(test_session_factory, request):
    """Backend setup consumed by storage-neutral repository contract tests."""
    postgres = {
        "source": PostgresSourceRepository,
        "evidence": PostgresEvidenceRepository,
        "prompt": PostgresPromptRepository,
        "scenario": PostgresScenarioRepository,
        "plan": PostgresPlanRepository,
        "signal": PostgresSignalRepository,
        "experiment": PostgresExperimentRepository,
        "planning": PostgresPlanningCycleRepository,
    }
    if request.param == "postgres":
        yield postgres
        return

    endpoint = os.getenv("DYNAMODB_LOCAL_ENDPOINT")
    if not endpoint:
        pytest.skip("set DYNAMODB_LOCAL_ENDPOINT to run DynamoDB repository contracts")
    from app.repositories.dynamodb import (
        DynamoEvidenceRepository, DynamoExperimentRepository, DynamoPlanRepository,
        DynamoPlanningCycleRepository, DynamoPromptRepository, DynamoScenarioRepository,
        DynamoSignalRepository, DynamoSourceRepository,
    )
    from app.repositories.dynamodb.config import require_local_endpoint
    from app.repositories.dynamodb.schema import create_table, delete_table

    resource = boto3.resource(
        "dynamodb", region_name="ap-southeast-1",
        endpoint_url=require_local_endpoint(endpoint),
        aws_access_key_id="localTestKey", aws_secret_access_key="localTestSecret",
    )
    table = create_table(resource, f"psa-contract-{uuid4().hex}")
    factories = {
        "source": lambda: DynamoSourceRepository(table),
        "evidence": lambda: DynamoEvidenceRepository(table),
        "prompt": lambda: DynamoPromptRepository(table),
        "scenario": lambda: DynamoScenarioRepository(table),
        "plan": lambda: DynamoPlanRepository(table),
        "signal": lambda: DynamoSignalRepository(table),
        "experiment": lambda: DynamoExperimentRepository(table),
        "planning": lambda: DynamoPlanningCycleRepository(table),
    }
    yield factories
    delete_table(table)
