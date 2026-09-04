"""Contract tests for explicit, fail-closed persistence selection."""

import pytest

from app.repositories.contracts import Page
from app.repositories.factory import get_storage, reset_storage, selected_backend


@pytest.fixture(autouse=True)
def clear_storage_cache():
    reset_storage()
    yield
    reset_storage()


def test_postgres_is_the_local_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PERSISTENCE_BACKEND", raising=False)
    assert selected_backend() == "postgres"
    assert get_storage().backend == "postgres"


def test_backend_selection_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_BACKEND", " POSTGRES ")
    assert selected_backend() == "postgres"


def test_dynamodb_backend_requires_and_accepts_complete_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PERSISTENCE_BACKEND", "dynamodb")
    monkeypatch.delenv("DYNAMODB_TABLE_NAME", raising=False)
    with pytest.raises(Exception, match="DYNAMODB_TABLE_NAME"):
        get_storage()
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", "psa-runtime")
    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")
    assert get_storage().backend == "dynamodb"


def test_unknown_backend_fails_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_BACKEND", "automatic")
    with pytest.raises(RuntimeError, match="Unsupported PERSISTENCE_BACKEND"):
        get_storage()


def test_page_uses_an_opaque_optional_token() -> None:
    page = Page(items=("one", "two"), continuation_token="opaque")
    assert page.items == ("one", "two")
    assert page.continuation_token == "opaque"
