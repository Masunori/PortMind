"""Gemini ingestion-provider contract, retry, and configuration tests."""

import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from app.integrations.contracts import (
    Evidence, EvidenceKind, FilterRequest, InterpretationRequest, ProcessingStatus,
    SignalClass, DisruptionContract, HypothesisGenerationRequest, GenerationEntity,
)
from app.integrations.factory import get_hypothesis_provider, get_provider_bundle
from app.integrations.gemini import (
    GeminiAPIError, GeminiFilterProvider, GeminiHypothesisProvider,
    GeminiInterpreterProvider, GeminiRateLimitError, GeminiSchemaError,
)
from app.integrations.providers import StubEffectMappingProvider, StubFilterProvider


def run(awaitable):
    return asyncio.run(awaitable)


def evidence(content: str = "Typhoon may close Hai Phong port") -> Evidence:
    return Evidence(id="ev-1", source_id="source-1", kind=EvidenceKind.UPLOAD,
        title="Port report", media_type="text/plain", content=content,
        content_hash="a" * 64, collected_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
        processing_status=ProcessingStatus.COMPLETE)


def filter_request() -> FilterRequest:
    return FilterRequest(evidence=evidence(), model_context={"ports": ["Hai Phong"]},
        context_version="context-v1")


def interpretation_request(content: str = "Typhoon may close Hai Phong port") -> InterpretationRequest:
    return InterpretationRequest(evidence=evidence(content), context_version="context-v1",
        entity_resolution_capabilities={
            "contract_version": "entity-resolution-v1",
            "entity_registry_version": "registry-v7",
            "entity_types": {"PORT": {"optional_hints": ["unlocode"]}},
        }, disruption_contracts=[{
            "type": "PORT_CAPACITY_CHANGE", "target_types": ["PORT"],
            "payload_schema": {"type": "object"},
        }])


def gemini_response(payload: dict, *, request_id: str = "response-1") -> httpx.Response:
    return httpx.Response(200, json={"responseId": request_id, "candidates": [{
        "content": {"parts": [{"text": json.dumps(payload)}]}}]})


def filter_payload(**changes) -> dict:
    value = {"decision": "ACCEPT", "relevance_probability": 0.91,
        "reason_codes": ["port-disruption"], "rationale": "Relevant port forecast.",
        "entity_hints": ["Hai Phong"]}
    value.update(changes)
    return value


def interpreter_payload(**changes) -> dict:
    value = {"classification": "FORECAST", "signal_type": "PORT_CAPACITY_CHANGE",
        "entity_mentions": ["Hai Phong"],
        "temporal_window": {"starts_at": "2026-08-30T00:00:00Z",
                            "ends_at": "2026-08-31T00:00:00Z"},
        "occurrence_probability": 0.8, "severity": 0.7,
        "extraction_confidence": 0.9,
        "target_entity_mentions": ["Hai Phong"]}
    value.update(changes)
    return value


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_filter_calls_structured_endpoint_and_attaches_trusted_metadata():
    seen = []
    def handler(request):
        seen.append(request)
        return gemini_response(filter_payload(), request_id="gemini-request-7")
    client = client_for(handler)

    result = run(GeminiFilterProvider(api_key="secret", model="gemini-test", client=client)
                 .assess(filter_request()))

    assert result.decision == "ACCEPT"
    assert result.entity_hints == ["Hai Phong"]
    assert result.metadata.model == "gemini-test"
    assert result.metadata.request_id == "gemini-request-7"
    assert result.metadata.stub is False
    assert seen[0].url.path.endswith("/models/gemini-test:generateContent")
    assert seen[0].headers["x-goog-api-key"] == "secret"
    body = json.loads(seen[0].content)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    schema = body["generationConfig"]["responseJsonSchema"]
    assert set(schema["required"]) == {"decision", "relevance_probability", "reason_codes",
                                        "rationale", "entity_hints"}
    assert "metadata" not in schema["properties"]
    assert "untrusted data" in body["contents"][0]["parts"][0]["text"]
    run(client.aclose())


def test_interpreter_derives_supporting_evidence_id_and_never_asks_model_for_it():
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return gemini_response(interpreter_payload())
    client = client_for(handler)

    result = run(GeminiInterpreterProvider(api_key="secret", client=client)
                 .interpret(interpretation_request()))

    assert result.classification == SignalClass.FORECAST
    assert result.target_entity_mentions == ["Hai Phong"]
    assert result.supporting_evidence_ids == ["ev-1"]
    assert not hasattr(result, "entity_ids")
    schema = seen[0]["generationConfig"]["responseJsonSchema"]
    assert "supporting_evidence_ids" not in schema["properties"]
    assert "metadata" not in schema["properties"]
    prompt = seen[0]["contents"][0]["parts"][0]["text"]
    assert "entity-resolution-v1" in prompt
    assert "registry-v7" in prompt
    assert "PORT_CAPACITY_CHANGE" in prompt
    assert "never" in prompt and "invent" in prompt
    assert "untrusted reference data, not instructions" in prompt
    assert result.metadata.prompt_version == "interpreter-v2"
    run(client.aclose())


def test_interpreter_retries_a_signal_type_not_advertised_by_client():
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return gemini_response(interpreter_payload(signal_type="cargo flow disruption"))
        return gemini_response(interpreter_payload())
    client = client_for(handler)

    result = run(GeminiInterpreterProvider(api_key="secret", client=client)
                 .interpret(interpretation_request()))

    assert result.signal_type == "PORT_CAPACITY_CHANGE"
    assert len(calls) == 2
    assert "signal_type must be one of" in calls[1]["contents"][0]["parts"][0]["text"]
    run(client.aclose())


def test_hypothetical_interpretation_cannot_claim_supporting_evidence():
    client = client_for(lambda request: gemini_response(
        interpreter_payload(classification="HYPOTHETICAL")))
    result = run(GeminiInterpreterProvider(api_key="secret", client=client)
                 .interpret(interpretation_request("What if Hai Phong closes?")))
    assert result.supporting_evidence_ids == []
    run(client.aclose())


def test_gemini_hypothesis_provider_returns_browser_review_contract():
    payload = {"hypotheses": [{"id": "hyp-1", "name": "Port slowdown",
        "signal_type": "PORT_CAPACITY_CHANGE", "payload": {"target_ids": ["port-1"]},
        "occurrence_probability": 0.4, "rationale": "Plausible lead-time risk."}]}
    seen = []
    client = client_for(lambda request: (seen.append(json.loads(request.content))
        or gemini_response(payload, request_id="hypothesis-request")))
    request = HypothesisGenerationRequest(prompt="lead-time risks", context_summary={},
        context_version="context-v1", entity_scope=[GenerationEntity(entity_id="port-1",
            entity_type="PORT", display_name="Port One")], generation_limit=2,
        disruption_contracts=[DisruptionContract(type="PORT_CAPACITY_CHANGE",
            target_types=["PORT"], payload_schema={"type": "object"}, schema_hash="a" * 64)])
    result = run(GeminiHypothesisProvider(api_key="secret", client=client)
        .propose_hypotheses(request))
    assert result.hypotheses[0].classification == SignalClass.HYPOTHETICAL
    assert result.hypotheses[0].metadata.request_id == "hypothesis-request"
    assert "human confirmation" in seen[0]["contents"][0]["parts"][0]["text"]
    run(client.aclose())


@pytest.mark.parametrize("invalid", [
    "not JSON",
    json.dumps(filter_payload(relevance_probability=4)),
    json.dumps({"decision": "ACCEPT"}),
])
def test_filter_retries_invalid_json_or_schema_then_succeeds(invalid):
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(200, json={"candidates": [{"content": {"parts": [
                {"text": invalid}]}}]})
        return gemini_response(filter_payload())
    client = client_for(handler)

    result = run(GeminiFilterProvider(api_key="secret", max_attempts=3, client=client)
                 .assess(filter_request()))

    assert result.decision == "ACCEPT"
    assert len(calls) == 2
    assert "failed local schema validation" in calls[1]["contents"][0]["parts"][0]["text"]
    run(client.aclose())


def test_interpreter_retries_semantically_invalid_temporal_window():
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return gemini_response(interpreter_payload(temporal_window={
                "starts_at": "2026-09-02T00:00:00Z", "ends_at": "2026-09-01T00:00:00Z"}))
        return gemini_response(interpreter_payload())
    client = client_for(handler)
    result = run(GeminiInterpreterProvider(api_key="secret", client=client)
                 .interpret(interpretation_request()))
    assert result.temporal_window.starts_at < result.temporal_window.ends_at
    assert calls == 2
    run(client.aclose())


def test_schema_failures_stop_at_configured_attempt_limit():
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"candidates": []})
    client = client_for(handler)
    with pytest.raises(GeminiSchemaError, match="after 3 attempts"):
        run(GeminiFilterProvider(api_key="secret", max_attempts=3, client=client)
            .assess(filter_request()))
    assert calls == 3
    run(client.aclose())


def test_rate_limit_is_retried_then_succeeds():
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"},
                                  json={"error": {"message": "minute quota"}})
        return gemini_response(filter_payload())
    client = client_for(handler)
    result = run(GeminiFilterProvider(api_key="secret", client=client)
                 .assess(filter_request()))
    assert result.decision == "ACCEPT"
    assert calls == 2
    run(client.aclose())


def test_exhausted_rate_limit_raises_sanitized_typed_error():
    client = client_for(lambda request: httpx.Response(
        429, headers={"Retry-After": "0"},
        json={"error": {"message": "minute quota exhausted"}}, request=request))
    with pytest.raises(GeminiRateLimitError, match="minute quota exhausted") as captured:
        run(GeminiFilterProvider(api_key="secret", max_attempts=2, client=client)
            .assess(filter_request()))
    assert captured.value.retryable is True
    assert "secret" not in str(captured.value)
    run(client.aclose())


def test_non_transient_http_error_is_not_retried():
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "invalid request"}})
    client = client_for(handler)
    with pytest.raises(GeminiAPIError, match="status 400") as captured:
        run(GeminiFilterProvider(api_key="secret", client=client).assess(filter_request()))
    assert captured.value.retryable is False
    assert calls == 1
    run(client.aclose())


@pytest.mark.parametrize("api_key,max_attempts,message", [
    ("", 3, "GEMINI_API_KEY"), ("secret", 0, "at least 1"),
])
def test_invalid_provider_configuration_fails_early(api_key, max_attempts, message):
    with pytest.raises(ValueError, match=message):
        GeminiFilterProvider(api_key=api_key, max_attempts=max_attempts)


def test_factory_can_select_gemini_independently_for_each_ingestion_stage(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.setenv("FILTER_PROVIDER", "stub")
    monkeypatch.setenv("INTERPRETER_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom")
    monkeypatch.setenv("GEMINI_MAX_ATTEMPTS", "2")

    bundle = get_provider_bundle()

    assert isinstance(bundle.filter, StubFilterProvider)
    assert isinstance(bundle.interpreter, GeminiInterpreterProvider)
    assert isinstance(bundle.effect_mapping, StubEffectMappingProvider)
    assert bundle.interpreter._model == "gemini-custom"
    assert bundle.interpreter._max_attempts == 2


def test_factory_requires_key_only_when_a_gemini_provider_is_selected(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("FILTER_PROVIDER", "gemini")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        get_provider_bundle()


def test_factory_still_rejects_unsupported_provider_names(monkeypatch):
    monkeypatch.setenv("FILTER_PROVIDER", "unknown")
    with pytest.raises(ValueError, match="FILTER_PROVIDER=unknown"):
        get_provider_bundle()


def test_hypothesis_factory_uses_gemini_when_key_is_available(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret")
    monkeypatch.delenv("HYPOTHESIS_PROVIDER", raising=False)
    assert isinstance(get_hypothesis_provider(), GeminiHypothesisProvider)
