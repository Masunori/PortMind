"""Runtime gateway selection must never access local operational data."""

import pytest

from app.integrations.factory import get_client_gateway
from app.integrations.gateway import HTTPClientGateway


def test_runtime_factory_requires_client_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLIENT_GATEWAY_URL", raising=False)
    monkeypatch.setenv("CLIENT_GATEWAY", "local")
    with pytest.raises(ValueError, match="HTTP-only"):
        get_client_gateway()


def test_runtime_factory_always_returns_http_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLIENT_GATEWAY_URL", "http://demo-client/integration/v1")
    monkeypatch.setenv("CLIENT_GATEWAY", "local")
    assert isinstance(get_client_gateway(), HTTPClientGateway)
