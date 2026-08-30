"""Contract and gateway regression tests for the platform/client boundary."""

import asyncio
from datetime import datetime, timezone

import httpx
import pytest
from pydantic import ValidationError

from app.integrations.contracts import (
    EntityCandidate, EntityResolveRequest, Evidence, EvidenceKind, FilterRequest,
    InterpretationRequest, ProcessingStatus, SignalClass, SimulationSubmission,
    DisruptionReconciliationRequest, DisruptionReconciliationItem,
    DisruptionValidationRequest,
)
from app.integrations.errors import ClientAuthenticationError, ClientContractError, StaleClientContextError
from app.integrations.gateway import HTTPClientGateway
from app.integrations.providers import StubFilterProvider, StubInterpreterProvider
from tests.fakes import FakeClientGateway


def run(awaitable):
    return asyncio.run(awaitable)


def evidence(content: str = "Typhoon may close Hai Phong port") -> Evidence:
    return Evidence(id="ev-1", source_id="source-1", kind=EvidenceKind.UPLOAD,
        title="Report", media_type="text/plain", content=content, content_hash="a" * 64,
        collected_at=datetime.now(timezone.utc), processing_status=ProcessingStatus.COMPLETE)


def test_evidence_is_strict_and_requires_a_content_form():
    values = evidence().model_dump()
    values["unexpected"] = True
    with pytest.raises(ValidationError): Evidence.model_validate(values)
    values.pop("unexpected")
    values["content"] = None
    with pytest.raises(ValidationError, match="requires content"): Evidence.model_validate(values)


def test_stub_filter_and_interpreter_keep_thresholds_and_ids_outside_provider():
    item = evidence()
    filtered = run(StubFilterProvider().assess(FilterRequest(evidence=item, model_context={}, context_version="v1")))
    interpreted = run(StubInterpreterProvider().interpret(InterpretationRequest(
        evidence=item, context_version="v1", disruption_contracts=[{
            "type": "PORT_CAPACITY_CHANGE", "target_types": ["PORT"],
            "payload_schema": {"type": "object"},
        }])))
    assert filtered.decision == "ACCEPT"
    assert filtered.metadata.stub is True
    assert interpreted.classification == SignalClass.FORECAST
    assert interpreted.entity_mentions == ["Hai Phong"]
    assert interpreted.target_entity_mentions == ["Hai Phong"]
    assert not hasattr(interpreted, "entity_ids")


def test_hypothetical_provider_output_cannot_claim_evidence():
    interpreted = run(StubInterpreterProvider().interpret(
        InterpretationRequest(evidence=evidence("Hypothetical: what if Hai Phong closes?"),
            context_version="v1", disruption_contracts=[{
                "type": "PORT_CAPACITY_CHANGE", "target_types": ["PORT"],
                "payload_schema": {"type": "object"},
            }])))
    assert interpreted.classification == SignalClass.HYPOTHETICAL
    assert interpreted.supporting_evidence_ids == []


def test_fake_gateway_supports_grounding_and_two_stage_validation():
    gateway = FakeClientGateway(entities=[EntityCandidate(
        entity_id="hph", entity_type="port", display_name="Hai Phong", confidence=1)])
    context = run(gateway.get_context())
    resolved = run(gateway.resolve_entity(EntityResolveRequest(
        mention="hai phong", context_version=context.context_version)))
    assert resolved.status == "RESOLVED"
    assert resolved.entity.entity_id == "hph"
    catalog = run(gateway.get_disruption_contracts())
    contract = next(item for item in catalog.contracts if item.type == "PORT_CAPACITY_CHANGE")
    assert contract.schema_hash


def test_fake_gateway_supports_deterministic_failures_and_submission():
    gateway = FakeClientGateway()
    gateway.fail("resolve_entity", StaleClientContextError("stale"))
    with pytest.raises(StaleClientContextError):
        run(gateway.resolve_entity(EntityResolveRequest(
            mention="Hai Phong", context_version="stale")))
    gateway.failures.clear()
    context = run(gateway.get_context())
    request = SimulationSubmission(experiment_id="x", idempotency_key="stable-key", context_version=context.context_version,
        state_version=context.state_version, signal_version_ids=["sv-1"], disruptions=[], occurrence_probability=0.5,
        provenance={})
    assert run(gateway.submit_simulation(request)).run_id == "fake-run-1"


@pytest.mark.parametrize("status,error", [(401, ClientAuthenticationError), (409, StaleClientContextError)])
def test_http_gateway_maps_stable_errors(status, error):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={"detail": "secret"}))
    client = httpx.AsyncClient(transport=transport, base_url="http://client/integration/v1")
    gateway = HTTPClientGateway("http://client/integration/v1", client=client, max_retries=0)
    with pytest.raises(error): run(gateway.get_context())
    run(client.aclose())


def test_http_gateway_rejects_malformed_client_response():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"context_version": "missing fields"}))
    client = httpx.AsyncClient(transport=transport, base_url="http://client/integration/v1")
    with pytest.raises(ClientContractError):
        run(HTTPClientGateway("http://client/integration/v1", client=client).get_context())
    run(client.aclose())


def test_http_gateway_fetches_entity_resolution_capabilities_from_integration_base():
    seen = []
    response = {
        "contract_version": "entity-resolution-v2",
        "entity_registry_version": "registry-v9",
        "entity_types": {"PORT": {"optional_hints": ["unlocode"]}},
        "examples": [{"mention": "Port of Singapore", "expected_type": "PORT"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                               base_url="http://client/integration/v1")
    result = run(HTTPClientGateway("http://client/integration/v1", client=client)
                 .get_entity_resolution_capabilities())

    assert seen[0].url.path == "/integration/v1/entity-resolution/capabilities"
    assert result.contract_version == "entity-resolution-v2"
    assert result.entity_registry_version == "registry-v9"
    assert result.manifest == response
    run(client.aclose())


def test_http_gateway_rejects_malformed_entity_resolution_capabilities():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"contract_version": "v1"})),
        base_url="http://client/integration/v1")
    with pytest.raises(ClientContractError, match="entity-resolution capabilities"):
        run(HTTPClientGateway("http://client/integration/v1", client=client)
            .get_entity_resolution_capabilities())
    run(client.aclose())


def test_http_gateway_sends_disruption_catalog_version():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"valid": True,
            "normalized_disruption": seen["disruption"]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://client")
    request = DisruptionValidationRequest(disruption_type="PORT_CAPACITY_CHANGE",
        payload={"target_ids": ["port-1"]}, catalog_version="catalog-v4",
        context_version="context-v1", schema_hash="a" * 64)
    result = run(HTTPClientGateway("http://client", client=client).validate_disruption(request))
    assert result.valid is True
    assert seen["catalog_version"] == "catalog-v4"
    run(client.aclose())


def test_http_gateway_applies_bearer_correlation_and_idempotency_headers():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json={"id": "run-1", "status": "QUEUED",
                                         "idempotent_replay": False})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                               base_url="http://client/integration/v1")
    request = SimulationSubmission(experiment_id="experiment-1", idempotency_key="stable-key",
        context_version="context-v1", state_version="state-v1", signal_version_ids=["signal-v1"],
        disruptions=[], occurrence_probability=0.5, provenance={})
    gateway = HTTPClientGateway("http://client/integration/v1", token="token-value", client=client)
    run(gateway.submit_simulation(request))
    assert seen[0].url.path == "/integration/v1/simulations"
    assert seen[0].headers["authorization"] == "Bearer token-value"
    assert seen[0].headers["idempotency-key"] == "stable-key"
    assert seen[0].headers["x-correlation-id"]
    run(client.aclose())


def test_http_gateway_sends_complete_scenario_and_only_active_disruptions():
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(202, json={"id": "run-1", "status": "QUEUED"})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://client")
    request = SimulationSubmission(experiment_id="experiment-1", idempotency_key="stable-key",
        context_version="context-v1", state_version="state-v1", signal_version_ids=["signal-v1"],
        disruptions=[{"type": "PORT_CAPACITY_CHANGE", "payload": {"target_ids": ["port-1"]}}],
        scenario_disruptions=[{"disruption_id": "signal-v1", "classification": "OBSERVED",
            "source_signal_version_id": "signal-v1", "application_status": "ALREADY_REFLECTED",
            "type": "PORT_CAPACITY_CHANGE", "payload": {"target_ids": ["port-1"]},
            "reason_code": "PRESENT_IN_FROZEN_STATE"}],
        active_disruptions=[], occurrence_probability=0.5,
        provenance={"planning_cycle_id": "cycle-1"})
    run(HTTPClientGateway("http://client", client=client).submit_simulation(request))
    assert seen["scenario_disruptions"] == [{
        "disruption_id": "signal-v1", "classification": "OBSERVED",
        "source_signal_version_id": "signal-v1", "application_status": "ALREADY_REFLECTED",
        "normalized_disruption": {"type": "PORT_CAPACITY_CHANGE",
                                  "payload": {"target_ids": ["port-1"]}},
        "reason_code": "PRESENT_IN_FROZEN_STATE"}]
    assert seen["disruptions"] == []
    assert seen["experiment_id"] == "experiment-1"
    assert seen["provenance"] == {"planning_cycle_id": "cycle-1"}
    run(client.aclose())


def test_http_gateway_keeps_legacy_submission_out_of_reconciled_scenario():
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(202, json={"id": "run-1", "status": "QUEUED"})
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://client")
    disruption = {"type": "PORT_CAPACITY_CHANGE", "payload": {"target_ids": ["port-1"]}}
    request = SimulationSubmission(experiment_id="experiment-1", idempotency_key="stable-key",
        context_version="context-v1", state_version="state-v1", signal_version_ids=["signal-v1"],
        disruptions=[disruption], occurrence_probability=0.5, provenance={})
    run(HTTPClientGateway("http://client", client=client).submit_simulation(request))
    assert seen["disruptions"] == [disruption]
    assert seen["scenario_disruptions"] == []
    run(client.aclose())
