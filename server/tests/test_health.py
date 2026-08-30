"""Unit tests for application and database health endpoints."""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app import main
from app.integrations.errors import ClientAuthenticationError
from tests.fakes import FakeClientGateway


class WorkingConnection:
    """Minimal successful SQLAlchemy connection test double."""

    def __enter__(self):
        """Enter the fake connection context."""

        return self

    def __exit__(self, *args: object) -> None:
        """Exit the fake connection context without suppressing errors."""

        return None

    def execute(self, statement: object) -> None:
        """Assert that the health check executes the expected probe."""

        assert str(statement) == "SELECT 1"


class WorkingEngine:
    """Engine test double that returns a working connection."""

    def connect(self) -> WorkingConnection:
        """Return a context-managed working connection."""

        return WorkingConnection()


class BrokenEngine:
    """Engine test double that raises a SQLAlchemy connection error."""

    def connect(self) -> None:
        """Simulate a failed attempt to establish a connection."""

        raise SQLAlchemyError("database down")


def test_application_health() -> None:
    """The process health endpoint reports success without dependencies."""

    assert asyncio.run(main.health()) == {"status": "ok"}


def test_client_health_reports_versions_without_credentials() -> None:
    result = asyncio.run(main.client_health(FakeClientGateway()))
    assert result | {"last_successful_response_at": "checked"} == {
        "status": "ok", "client_id": "fake-client",
        "context_version": "context-v1", "schema_version": "schema-v1",
        "state_version": "state-v1", "capability_version": "capability-v1",
        "last_successful_response_at": "checked", "error_code": None,
    }


def test_client_health_sanitizes_gateway_failures() -> None:
    gateway = FakeClientGateway()
    gateway.fail("get_context", ClientAuthenticationError("secret upstream response"))
    result = asyncio.run(main.client_health(gateway))
    assert result["status"] == "degraded"
    assert result["error_code"] == "CLIENT_AUTHENTICATION_ERROR"
    assert "secret" not in str(result)


def test_database_health_when_connection_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Database health reports success after executing its probe query."""

    monkeypatch.setattr(main, "engine", WorkingEngine())

    assert main.database_health() == {"status": "ok", "database": "ok"}


def test_database_health_returns_503_when_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Database connection errors are translated into HTTP 503."""

    monkeypatch.setattr(main, "engine", BrokenEngine())

    with pytest.raises(HTTPException) as caught:
        main.database_health()

    assert caught.value.status_code == 503
    assert caught.value.detail == "database unavailable"
