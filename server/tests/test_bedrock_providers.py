"""Bedrock Converse provider, schema, error, and factory tests."""

import asyncio
import json
import os
from datetime import datetime, timezone

import pytest
from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError

from app.integrations.bedrock import (
    BedrockAPIError, BedrockFilterProvider, BedrockHypothesisProvider, BedrockInterpreterProvider,
    BedrockPlannerPanelProvider, BedrockPlannerProvider, BedrockRateLimitError,
    BedrockRiskProvider, BedrockSchemaError, _bedrock_output_schema,
)
from app.integrations.contracts import (
    DisruptionContract, Evidence, EvidenceKind, FilterRequest, GenerationEntity,
    HypothesisGenerationRequest, InterpretationRequest, PlannerRequest,
    ProcessingStatus, RiskGenerationRequest, SignalClass,
)
from app.integrations.factory import (
    get_hypothesis_provider, get_planner_provider, get_provider_bundle, get_risk_provider,
)
from app.integrations.model_provider import (
    FilterOutput, HypothesisOutput, InterpreterOutput, PlannerOutput, RiskOutput,
)


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.mark.parametrize("output_type", [
    FilterOutput, InterpreterOutput, HypothesisOutput, RiskOutput, PlannerOutput,
])
def test_all_bedrock_output_schemas_exclude_unsupported_constraints(output_type):
    forbidden = {
        "default", "maximum", "maxItems", "maxLength", "minimum",
        "minLength", "multipleOf",
    }
    errors = []

    def inspect(value, path="$"):
        if isinstance(value, list):
            for index, item in enumerate(value):
                inspect(item, f"{path}[{index}]")
            return
        if not isinstance(value, dict):
            return
        for key, item in value.items():
            if key in forbidden:
                errors.append(f"{path}.{key}")
            if key == "additionalProperties" and item is not False:
                errors.append(f"{path}.{key}={item!r}")
            if key == "minItems" and item not in (0, 1):
                errors.append(f"{path}.{key}={item!r}")
            inspect(item, f"{path}.{key}")

    inspect(_bedrock_output_schema(output_type))
    assert errors == []


class FakeBedrockClient:
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def converse(self, **request):
        self.calls.append(request)
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        if "toolConfig" in request:
            name = request["toolConfig"]["toolChoice"]["tool"]["name"]
            content = [{"toolUse": {
                "toolUseId": "tool-use-1", "name": name, "input": payload,
            }}]
        else:
            content = [
                {"text": payload if isinstance(payload, str) else json.dumps(payload)}
            ]
        return {"output": {"message": {"role": "assistant", "content": content}},
                "ResponseMetadata": {"RequestId": "bedrock-request-1"}}


def evidence() -> Evidence:
    return Evidence(id="ev-1", source_id="source-1", kind=EvidenceKind.UPLOAD,
        title="Port report", media_type="text/plain",
        content="Typhoon may close Hai Phong port", content_hash="a" * 64,
        collected_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
        processing_status=ProcessingStatus.COMPLETE)


def filter_payload():
    return {"decision": "ACCEPT", "relevance_probability": 0.91,
        "reason_codes": ["port-disruption"], "rationale": "Relevant forecast.",
        "entity_hints": ["Hai Phong"]}


def interpreter_payload():
    return {"classification": "FORECAST", "signal_type": "PORT_CAPACITY_CHANGE",
        "entity_mentions": ["Hai Phong"], "target_entity_mentions": ["Hai Phong"],
        "temporal_window": {"starts_at": "2026-08-30T00:00:00Z",
                            "ends_at": "2026-08-31T00:00:00Z"},
        "occurrence_probability": 0.8, "severity": 0.7,
        "extraction_confidence": 0.9}


def test_filter_uses_converse_structured_output_and_trusted_metadata():
    client = FakeBedrockClient(filter_payload())
    result = run(BedrockFilterProvider(model="model-1", region="ap-southeast-1",
        client=client, system_prompt="Filter safely.").assess(FilterRequest(
            evidence=evidence(), model_context={"ports": ["Hai Phong"]},
            context_version="context-v1")))

    assert result.decision == "ACCEPT"
    assert result.metadata.provider == "bedrock"
    assert result.metadata.model == "model-1"
    assert result.metadata.request_id == "bedrock-request-1"
    request = client.calls[0]
    assert request["modelId"] == "model-1"
    assert request["system"] == [{"text": "Filter safely."}]
    assert request["outputConfig"]["textFormat"]["type"] == "json_schema"
    schema = json.loads(request["outputConfig"]["textFormat"]["structure"]
                        ["jsonSchema"]["schema"])
    assert "metadata" not in schema["properties"]
    assert "minimum" not in schema["properties"]["relevance_probability"]
    assert "maximum" not in schema["properties"]["relevance_probability"]
    assert request["inferenceConfig"] == {"temperature": 0, "maxTokens": 4096}


def test_nova_2_uses_forced_tool_output_instead_of_unsupported_output_config():
    client = FakeBedrockClient(filter_payload())
    result = run(BedrockFilterProvider(
        model="us.amazon.nova-2-lite-v1:0", client=client,
    ).assess(FilterRequest(
        evidence=evidence(), model_context={}, context_version="context-v1",
    )))

    request = client.calls[0]
    assert "outputConfig" not in request
    assert request["toolConfig"]["toolChoice"] == {
        "tool": {"name": "filteroutput"},
    }
    assert request["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert result.relevance_probability == 0.91


def test_interpreter_preserves_grounding_boundary():
    client = FakeBedrockClient(interpreter_payload())
    request = InterpretationRequest(evidence=evidence(), context_version="context-v1",
        entity_resolution_capabilities={"entity_types": {"PORT": {}}},
        disruption_contracts=[{"type": "PORT_CAPACITY_CHANGE",
            "target_types": ["PORT"], "payload_schema": {"type": "object"}}])
    result = run(BedrockInterpreterProvider(model="model-1", client=client)
                 .interpret(request))
    assert result.classification == SignalClass.FORECAST
    assert result.supporting_evidence_ids == ["ev-1"]
    assert result.target_entity_mentions == ["Hai Phong"]
    assert result.metadata.prompt_version == "interpreter-v2"


def test_hypothesis_risk_and_planner_providers_use_bedrock():
    hypothesis_client = FakeBedrockClient({"hypotheses": [{"id": "hyp-1",
        "name": "Port slowdown", "signal_type": "PORT_CAPACITY_CHANGE",
        "payload": {"target_ids": ["port-1"]}, "occurrence_probability": 0.4,
        "rationale": "Plausible risk."}]})
    contract = DisruptionContract(type="PORT_CAPACITY_CHANGE", target_types=["PORT"],
        payload_schema={"type": "object"}, schema_hash="a" * 64)
    hypothesis = run(BedrockHypothesisProvider(model="model-1", client=hypothesis_client)
        .propose_hypotheses(HypothesisGenerationRequest(prompt="lead-time risks",
            context_summary={}, context_version="context-v1",
            entity_scope=[GenerationEntity(entity_id="port-1", entity_type="PORT",
                display_name="Port One")], generation_limit=1,
            disruption_contracts=[contract])))
    assert hypothesis.hypotheses[0].metadata.provider == "bedrock"

    risk_client = FakeBedrockClient({"proposals": [{"proposal_id": "risk-1",
        "name": "Port risk", "description": "Capacity scenario",
        "selected_signal_version_ids": [], "hypothetical_disruptions": [{
            "type": "PORT_CAPACITY_CHANGE",
            "payload_json": json.dumps({"target_ids": ["port-1"]})}],
        "occurrence_probability": 0.7, "assumptions": [],
        "rationale": "Capacity may fall."}], "warnings": []})
    risk = run(BedrockRiskProvider(model="model-1", client=risk_client)
        .propose_scenarios(RiskGenerationRequest(context_summary={},
            context_version="context-v1", state_version="state-v1",
            entity_scope=[GenerationEntity(entity_id="port-1", entity_type="PORT",
                display_name="Port One")],
            disruption_contracts=[contract], generation_limit=1)))
    assert risk.proposals[0].metadata.provider == "bedrock"

    planner_client = FakeBedrockClient({"proposals": [{"proposal_id": "plan-1",
        "name": "Reroute", "interventions": [{"type": "REROUTE",
            "payload_json": json.dumps({"target_ids": ["port-1"]})}],
        "rationale": "Protect continuity.", "assumptions": [],
        "expected_qualitative_effects": []}], "warnings": []})
    plan = run(BedrockPlannerProvider(model="model-1", client=planner_client)
        .propose_plans(PlannerRequest(planning_cycle_id="cycle-1",
            scenario_id="scenario-1", context_version="context-v1", state_version="state-v1",
            disruptions=[], baseline_run_id="run-1", baseline_results={},
            intervention_contracts=[{"type": "REROUTE", "target_types": ["PORT"],
                "payload_schema": {"type": "object"}, "schema_hash": "b" * 64}],
            proposal_limit=1, known_entity_ids=["port-1"])))
    assert plan.proposals[0].metadata.provider == "bedrock"


def test_invalid_response_gets_bounded_correction_attempt():
    client = FakeBedrockClient("not json", filter_payload())
    result = run(BedrockFilterProvider(model="model-1", max_attempts=2, client=client)
                 .assess(FilterRequest(evidence=evidence(), model_context={},
                                       context_version="context-v1")))
    assert result.decision == "ACCEPT"
    assert "failed local schema validation" in client.calls[1]["messages"][0]["content"][0]["text"]


def test_schema_failure_stops_at_attempt_limit():
    client = FakeBedrockClient("not json", "still not json")
    with pytest.raises(BedrockSchemaError, match="after 2 attempts"):
        run(BedrockFilterProvider(model="model-1", max_attempts=2, client=client)
            .assess(FilterRequest(evidence=evidence(), model_context={},
                                  context_version="context-v1")))


def test_throttling_is_sanitized_and_typed():
    error = ClientError({"Error": {"Code": "ThrottlingException",
        "Message": "request quota exceeded"},
        "ResponseMetadata": {"HTTPStatusCode": 429}}, "Converse")
    client = FakeBedrockClient(error)
    with pytest.raises(BedrockRateLimitError, match="quota exhausted") as captured:
        run(BedrockFilterProvider(model="model-1", client=client)
            .assess(FilterRequest(evidence=evidence(), model_context={},
                                  context_version="context-v1")))
    assert captured.value.status_code == 429
    assert captured.value.retryable is True


@pytest.mark.parametrize("error, status, retryable", [
    (ClientError({"Error": {"Code": "AccessDeniedException", "Message": "secret request"},
                  "ResponseMetadata": {"HTTPStatusCode": 403}}, "Converse"), 403, False),
    (ReadTimeoutError(endpoint_url="https://bedrock.invalid"), 503, True),
    (BotoCoreError(), 502, False),
])
def test_transport_failures_are_typed_without_reflecting_provider_details(
    error, status, retryable,
):
    client = FakeBedrockClient(error)
    with pytest.raises(BedrockAPIError) as captured:
        run(BedrockFilterProvider(model="model-1", client=client)
            .assess(FilterRequest(evidence=evidence(), model_context={},
                                  context_version="context-v1")))
    assert captured.value.status_code == status
    assert captured.value.retryable is retryable
    assert "secret request" not in str(captured.value)


def test_missing_response_blocks_use_the_bounded_schema_repair_path():
    class MissingBlockClient:
        def __init__(self):
            self.calls = 0

        def converse(self, **request):
            self.calls += 1
            return {"output": {"message": {"content": []}}}

    client = MissingBlockClient()
    with pytest.raises(BedrockSchemaError, match="after 2 attempts"):
        run(BedrockFilterProvider(model="model-1", max_attempts=2, client=client)
            .assess(FilterRequest(evidence=evidence(), model_context={},
                                  context_version="context-v1")))
    assert client.calls == 2


def test_semantic_validation_failure_can_be_corrected():
    invalid = interpreter_payload() | {"signal_type": "INVENTED"}
    client = FakeBedrockClient(invalid, interpreter_payload())
    request = InterpretationRequest(evidence=evidence(), context_version="context-v1",
        entity_resolution_capabilities={}, disruption_contracts=[{
            "type": "PORT_CAPACITY_CHANGE", "target_types": ["PORT"],
            "payload_schema": {"type": "object"}}])
    result = run(BedrockInterpreterProvider(model="model-1", max_attempts=2,
                                             client=client).interpret(request))
    assert result.signal_type == "PORT_CAPACITY_CHANGE"
    assert len(client.calls) == 2


def test_factories_select_bedrock_for_every_model_role(monkeypatch):
    monkeypatch.setenv("BEDROCK_MODEL_ID", "profile-1")
    monkeypatch.setenv("BEDROCK_REGION", "ap-southeast-1")
    monkeypatch.setenv("FILTER_PROVIDER", "bedrock")
    monkeypatch.setenv("INTERPRETER_PROVIDER", "bedrock")
    monkeypatch.setenv("RISK_PROVIDER", "bedrock")
    monkeypatch.setenv("PLANNER_PROVIDER", "bedrock")
    monkeypatch.setenv("HYPOTHESIS_PROVIDER", "bedrock")

    bundle = get_provider_bundle()
    assert isinstance(bundle.filter, BedrockFilterProvider)
    assert isinstance(bundle.interpreter, BedrockInterpreterProvider)
    assert isinstance(get_risk_provider(), BedrockRiskProvider)
    assert isinstance(get_planner_provider(), BedrockPlannerProvider)
    assert isinstance(get_planner_provider("panel", 2), BedrockPlannerPanelProvider)
    assert isinstance(get_hypothesis_provider(), BedrockHypothesisProvider)
    assert bundle.filter._model == "profile-1"
    assert bundle.filter._sdk_max_attempts == 2


def test_bedrock_planner_panel_labels_role_specific_proposals():
    payload = {"proposals": [{"proposal_id": "plan-1", "name": "Reroute",
        "interventions": [{"type": "REROUTE",
            "payload_json": json.dumps({"target_ids": ["port-1"]})}],
        "rationale": "Role-specific rationale.", "assumptions": [],
        "expected_qualitative_effects": []}], "warnings": []}
    client = FakeBedrockClient(payload, payload)
    provider = BedrockPlannerPanelProvider(model="model-1", client=client,
        agent_prompts=["Base planner prompt.", "Base planner prompt."], agent_count=2)
    result = run(provider.propose_plans(PlannerRequest(planning_cycle_id="cycle-1",
        scenario_id="scenario-1", context_version="context-v1", state_version="state-v1",
        disruptions=[], baseline_run_id="run-1", baseline_results={},
        intervention_contracts=[{"type": "REROUTE", "target_types": ["PORT"],
            "payload_schema": {"type": "object"}, "schema_hash": "b" * 64}],
        proposal_limit=2, known_entity_ids=["port-1"])))

    assert [item.proposal_id for item in result.proposals] == [
        "continuity-plan-1", "cost-plan-1"]
    assert all(item.metadata.provider == "bedrock-panel" for item in result.proposals)
    assert "Panel role: continuity." in client.calls[0]["system"][0]["text"]
    assert "Panel role: cost." in client.calls[1]["system"][0]["text"]


def test_bedrock_planner_panel_keeps_successful_partial_results():
    payload = {"proposals": [{"proposal_id": "plan-1", "name": "Reroute",
        "interventions": [{"type": "REROUTE", "payload_json": "{}"}],
        "rationale": "Role-specific rationale.", "assumptions": [],
        "expected_qualitative_effects": []}], "warnings": []}
    failure = ClientError({"Error": {"Code": "AccessDeniedException"},
                           "ResponseMetadata": {"HTTPStatusCode": 403}}, "Converse")
    client = FakeBedrockClient(payload, failure)
    provider = BedrockPlannerPanelProvider(model="model-1", client=client, agent_count=2)
    result = run(provider.propose_plans(PlannerRequest(planning_cycle_id="cycle-1",
        scenario_id="scenario-1", context_version="context-v1", state_version="state-v1",
        disruptions=[], baseline_run_id="run-1", baseline_results={},
        intervention_contracts=[{"type": "REROUTE", "target_types": ["PORT"],
            "payload_schema": {"type": "object"}, "schema_hash": "b" * 64}],
        proposal_limit=2, known_entity_ids=["port-1"])))
    assert [item.proposal_id for item in result.proposals] == ["continuity-plan-1"]
    assert result.warnings == ["cost: provider unavailable"]


def test_bedrock_configuration_requires_model_id():
    with pytest.raises(ValueError, match="BEDROCK_MODEL_ID"):
        BedrockFilterProvider(model="")


@pytest.mark.skipif(
    not (os.getenv("BEDROCK_LIVE_TEST") == "1" and os.getenv("BEDROCK_MODEL_ID")),
    reason="set BEDROCK_LIVE_TEST=1 and BEDROCK_MODEL_ID for the bounded AWS smoke test",
)
def test_live_bedrock_filter_smoke():
    """Opt-in live call capped at one attempt and 256 output tokens."""

    result = run(BedrockFilterProvider(
        model=os.environ["BEDROCK_MODEL_ID"],
        region=os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION"),
        max_attempts=1,
        sdk_max_attempts=1,
        timeout_seconds=20,
        max_tokens=256,
    ).assess(FilterRequest(evidence=evidence(), model_context={},
                           context_version="live-smoke-v1")))
    assert result.metadata.provider == "bedrock"


@pytest.mark.parametrize("target", ["invented-port", {"entity_id": "port-1"}, "vessel-1"])
def test_hypothesis_corrects_invalid_entity_targets(target):
    def payload(target_id):
        return {"hypotheses": [{"id": "hyp-1", "name": "Port slowdown",
            "signal_type": "PORT_CAPACITY_CHANGE", "payload": {"target_ids": [target_id]},
            "occurrence_probability": 0.4, "rationale": "Plausible risk."}]}

    client = FakeBedrockClient(payload(target), payload("port-1"))
    request = HypothesisGenerationRequest(prompt="port risks", context_summary={},
        context_version="context-v1", entity_scope=[
            GenerationEntity(entity_id="port-1", entity_type="PORT", display_name="Port One"),
            GenerationEntity(entity_id="vessel-1", entity_type="VESSEL", display_name="Vessel One")],
        disruption_contracts=[DisruptionContract(type="PORT_CAPACITY_CHANGE",
            target_types=["PORT"], payload_schema={"type": "object"}, schema_hash="a" * 64)])
    result = run(BedrockHypothesisProvider(model="us.amazon.nova-2-lite-v1:0", client=client)
        .propose_hypotheses(request))
    assert result.hypotheses[0].payload["target_ids"] == ["port-1"]
    assert len(client.calls) == 2
    assert "Validation errors" in client.calls[1]["messages"][0]["content"][0]["text"]


@pytest.mark.parametrize("target", ["invented-port", {"entity_id": "port-1"}, "vessel-1"])
def test_risk_corrects_invalid_disruption_targets(target, caplog):
    def payload(target_id):
        return {"proposals": [{"proposal_id": "risk-1", "name": "Port risk",
            "description": "Capacity scenario", "selected_signal_version_ids": [],
            "hypothetical_disruptions": [{"type": "PORT_CAPACITY_CHANGE",
                "payload_json": json.dumps({"target_ids": [target_id]})}],
            "occurrence_probability": 0.7, "assumptions": [],
            "rationale": "Capacity may fall."}], "warnings": []}

    client = FakeBedrockClient(payload(target), payload("port-1"))
    request = RiskGenerationRequest(context_summary={}, context_version="context-v1",
        state_version="state-v1", entity_scope=[
            GenerationEntity(entity_id="port-1", entity_type="PORT", display_name="Port One"),
            GenerationEntity(entity_id="vessel-1", entity_type="VESSEL", display_name="Vessel One")],
        disruption_contracts=[DisruptionContract(type="PORT_CAPACITY_CHANGE",
            target_types=["PORT"], payload_schema={"type": "object"}, schema_hash="a" * 64)])
    result = run(BedrockRiskProvider(model="us.amazon.nova-2-lite-v1:0", client=client)
        .propose_scenarios(request))
    assert result.proposals[0].hypothetical_disruptions[0].payload["target_ids"] == ["port-1"]
    assert len(client.calls) == 2
    assert "Validation errors" in client.calls[1]["messages"][0]["content"][0]["text"]

    first_prompt = client.calls[0]["messages"][0]["content"][0]["text"]
    assert 'Compatible entity IDs by disruption type: {"PORT_CAPACITY_CHANGE": ["port-1"]}' in first_prompt
    retry_prompt = client.calls[1]["messages"][0]["content"][0]["text"]
    assert 'strings copied exactly from ["port-1"]' in retry_prompt
    assert '"rejected_targets"' in caplog.text
    assert '"entity_type": "VESSEL"' in caplog.text


def test_missing_nova_tool_logs_diagnostics_and_corrects_prompt(caplog):
    class MissingToolClient:
        def __init__(self):
            self.calls = []

        def converse(self, **request):
            self.calls.append(request)
            return {"output": {"message": {"content": [{"text": "private response"}]}},
                "stopReason": "max_tokens", "usage": {"outputTokens": 4096},
                "ResponseMetadata": {"RequestId": "diagnostic-request"}}

    client = MissingToolClient()
    with pytest.raises(BedrockSchemaError, match="after 2 attempts"):
        run(BedrockFilterProvider(model="us.amazon.nova-2-lite-v1:0", max_attempts=2,
            client=client).assess(FilterRequest(evidence=evidence(), model_context={},
                context_version="context-v1")))
    assert "Missing expected toolUse.input for tool filteroutput" in client.calls[1]["messages"][0]["content"][0]["text"]
    records = [record for record in caplog.records if "Bedrock output validation failed" in record.message]
    assert len(records) == 2
    assert '"stop_reason": "max_tokens"' in records[0].message
    assert '"request_id": "diagnostic-request"' in records[0].message
    assert '"outputTokens": 4096' in records[0].message
    assert "private response" not in caplog.text


def test_validation_diagnostics_omit_model_payload(caplog):
    client = FakeBedrockClient({"private_field": "private response"})
    with pytest.raises(BedrockSchemaError):
        run(BedrockFilterProvider(model="model-1", max_attempts=1, client=client)
            .assess(FilterRequest(evidence=evidence(), model_context={}, context_version="context-v1")))
    assert "private response" not in caplog.text
    assert "missing" in caplog.text
