"""Purpose-specific provider protocols and deterministic development stubs."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from app.integrations.contracts import (
    EffectMappingProposal, EffectMappingRequest, FilterDecision, FilterRequest,
    FilterResult, InterpretationProposal, InterpretationRequest, ProviderMetadata,
    RelationshipProposal, RelationshipRequest, SignalClass, TemporalWindow,
    PlanProposal, PlannerRequest, PlannerResponse, ProposedDisruption,
    ProposedIntervention, RiskGenerationRequest, RiskGenerationResponse,
    RiskScenarioProposal, HypothesisGenerationRequest, HypothesisGenerationResponse,
    HypothesisSignalProposal,
)


class FilterProvider(Protocol):
    """Assess whether canonical evidence should enter signal processing."""

    async def assess(self, request: FilterRequest) -> FilterResult: ...


class InterpreterProvider(Protocol):
    """Extract a proposed signal from evidence without resolving entities."""

    async def interpret(self, request: InterpretationRequest) -> InterpretationProposal: ...


class EffectMappingProvider(Protocol):
    """Map a grounded signal onto a client-advertised disruption contract."""

    async def propose_mapping(self, request: EffectMappingRequest) -> EffectMappingProposal: ...


class RelationshipProvider(Protocol):
    """Infer a supported semantic relationship between signal versions."""

    async def propose_relationship(self, request: RelationshipRequest) -> RelationshipProposal: ...


class RiskProvider(Protocol):
    async def propose_scenarios(self, request: RiskGenerationRequest) -> RiskGenerationResponse: ...


class PlannerProvider(Protocol):
    async def propose_plans(self, request: PlannerRequest) -> PlannerResponse: ...


class HypothesisProvider(Protocol):
    async def propose_hypotheses(
        self, request: HypothesisGenerationRequest,
    ) -> HypothesisGenerationResponse: ...


def _metadata(component: str) -> ProviderMetadata:
    return ProviderMetadata(provider="stub", model=f"deterministic-{component}", prompt_version="v1", stub=True)


class StubFilterProvider:
    """Classify fixture keywords without an SDK, key, or hidden threshold."""

    async def assess(self, request: FilterRequest) -> FilterResult:
        text = " ".join(filter(None, [request.evidence.title, request.evidence.content or ""])).casefold()
        if "[malformed]" in text: raise ValueError("Stub malformed output")
        if "[timeout]" in text: raise TimeoutError("Stub timeout")
        if "[failure]" in text: raise RuntimeError("Stub failure")
        quarantine = any(word in text for word in ("malware", "prompt injection", "ignore previous instructions"))
        relevant = any(word in text for word in ("port", "shipment", "supplier", "closure", "delay", "typhoon"))
        ambiguous = "[ambiguous]" in text
        decision = FilterDecision.QUARANTINE if quarantine else FilterDecision.REVIEW if ambiguous else FilterDecision.ACCEPT if relevant else FilterDecision.REJECT
        probability = 0.0 if quarantine else 0.5 if ambiguous else 0.9 if relevant else 0.1
        return FilterResult(decision=decision, relevance_probability=probability,
            reason_codes=[decision.value.casefold()], rationale=f"Deterministic stub classified evidence as {decision.value}.",
            entity_hints=[name for name in ("Hai Phong", "Singapore") if name.casefold() in text], metadata=_metadata("filter"))


class StubInterpreterProvider:
    """Return transparent fixture facts and never trusted client identifiers."""

    async def interpret(self, request: InterpretationRequest) -> InterpretationProposal:
        text = " ".join(filter(None, [request.evidence.title, request.evidence.content or ""])).casefold()
        mentions = [name for name in (
            "Hai Phong", "Supplier VN", "PSA Singapore",
            "Singapore Warehouse", "Customer SG",
        ) if name.casefold() in text]
        observed = any(word in text for word in ("has closed", "is closed", "observed"))
        hypothetical = "what if" in text or "hypothetical" in text
        classification = SignalClass.HYPOTHETICAL if hypothetical else SignalClass.OBSERVED if observed else SignalClass.FORECAST
        allowed_types = {item.type for item in request.disruption_contracts}
        preferred = "PORT_CAPACITY_CHANGE" if "clos" in text else None
        signal_type = (preferred if preferred in allowed_types else
                       sorted(allowed_types)[0] if allowed_types else "UNKNOWN")
        starts_at = request.evidence.published_at or request.evidence.collected_at
        return InterpretationProposal(classification=classification, signal_type=signal_type,
            entity_mentions=mentions,
            target_entity_mentions=mentions[:1],
            temporal_window=TemporalWindow(starts_at=starts_at, ends_at=starts_at + timedelta(days=1)),
            occurrence_probability=1 if observed else 0.7,
            severity=0.7 if signal_type != "UNKNOWN" else 0, extraction_confidence=0.85 if signal_type != "UNKNOWN" else 0,
            supporting_evidence_ids=[] if hypothetical else [request.evidence.id], metadata=_metadata("interpreter"))


class StubEffectMappingProvider:
    """Map supported signal types to the strict demo disruption payload."""

    async def propose_mapping(self, request: EffectMappingRequest) -> EffectMappingProposal:
        parameters_schema = request.contract.payload_schema.get("properties", {}).get(
            "parameters", {"type": "object", "properties": {}, "required": []})
        parameters = _stub_mapping_value(parameters_schema, request.severity)
        return EffectMappingProposal(disruption_type=request.contract.type, payload={
            "target_ids": request.resolved_entity_ids,
            "effective_from": (request.temporal_window.starts_at.isoformat()
                               if request.temporal_window.starts_at else None),
            "effective_until": (request.temporal_window.ends_at.isoformat()
                                if request.temporal_window.ends_at else None),
            "parameters": parameters,
        }, mapping_confidence=0.9 if request.resolved_entity_ids else 0.2,
            metadata=_metadata("effect-mapping"))


def _stub_mapping_value(schema: dict, severity: float, field_name: str | None = None):
    """Build deterministic, schema-shaped required mapping values.

    Numeric fields scale across their advertised range so the fixture remains both
    valid and operationally meaningful for contracts such as delay hours.
    """

    if "const" in schema:
        return schema["const"]
    if schema.get("enum"):
        return schema["enum"][0]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((item for item in kind if item != "null"), "null")
    if kind == "object":
        return {
            name: _stub_mapping_value(child, severity, name)
            for name, child in schema.get("properties", {}).items()
            if name in schema.get("required", [])
        }
    if kind == "array":
        return [
            _stub_mapping_value(schema.get("items", {}), severity)
            for _ in range(schema.get("minItems", 0))
        ]
    if kind in {"number", "integer"}:
        minimum = schema.get("minimum", 0)
        maximum = schema.get("maximum")
        scale = 1 - severity if field_name == "capacity_multiplier" else severity
        value = minimum if maximum is None else minimum + scale * (maximum - minimum)
        return int(round(value)) if kind == "integer" else value
    if kind == "string":
        return "stub"
    if kind == "boolean":
        return severity >= 0.5
    return None


class StubRelationshipProvider:
    """Infer only exact-summary relationships for deterministic development."""

    async def propose_relationship(self, request: RelationshipRequest) -> RelationshipProposal:
        same = request.source_summary.casefold().strip() == request.target_summary.casefold().strip()
        return RelationshipProposal(relationship="SAME_EVENT_AS" if same else None,
            confidence=1 if same else 0, rationale="Exact normalized summary match." if same else "No deterministic relationship.",
            metadata=_metadata("relationship"))


def _fixture_failure(marker: str | None) -> None:
    marker = (marker or "").casefold()
    if marker == "timeout": raise TimeoutError("Stub timeout")
    if marker == "failure": raise RuntimeError("Stub failure")
    if marker == "malformed": raise ValueError("Stub malformed output")


def _stub_value(schema: dict, entity_ids: list[str], field_name: str | None = None):
    """Construct a minimal deterministic fixture value from an advertised schema."""
    if "const" in schema: return schema["const"]
    if schema.get("enum"): return schema["enum"][0]
    kind = schema.get("type")
    if isinstance(kind, list):
        concrete_kinds = [item for item in kind if item != "null"]
        if not concrete_kinds: return None
        kind = concrete_kinds[0]
    if kind == "object":
        return {name: (_stub_value(child, entity_ids, name) if name != "target_ids" else sorted(entity_ids)[:1])
                for name, child in sorted(schema.get("properties", {}).items())
                if name in schema.get("required", [])}
    if kind == "array": return []
    if kind == "string":
        if schema.get("format") == "date-time":
            return "2000-01-02T00:00:00+00:00" if field_name == "effective_until" else "2000-01-01T00:00:00+00:00"
        return "stub"
    if kind in {"number", "integer"}: return schema.get("minimum", 0)
    if kind == "boolean": return False
    return None


class StubRiskProvider:
    """Select only supplied contracts and entity IDs with stable output."""

    async def propose_scenarios(self, request: RiskGenerationRequest) -> RiskGenerationResponse:
        _fixture_failure(request.fixture_marker)
        metadata = _metadata("risk")
        if request.fixture_marker == "empty" or request.generation_limit == 0 or not request.disruption_contracts:
            return RiskGenerationResponse(metadata=metadata)
        contract = sorted(request.disruption_contracts, key=lambda item: item.type)[0]
        valid_types = {item.casefold() for item in contract.target_types}
        compatible = [item.entity_id for item in request.entity_scope
                      if item.entity_type.casefold() in valid_types]
        target_ids = sorted(compatible)[:1]
        hypothetical = ([ProposedDisruption(type=contract.type,
            payload=_stub_value(contract.payload_schema, target_ids))] if target_ids else [])
        selected = [item.signal_version_id for item in
                    sorted(request.candidate_signals, key=lambda item: item.signal_version_id)]
        if not selected and not hypothetical:
            return RiskGenerationResponse(metadata=metadata)
        proposal = RiskScenarioProposal(proposal_id="stub-risk-1", name="Deterministic risk scenario",
            description="Scenario selected from advertised client capabilities.",
            selected_signal_version_ids=selected,
            hypothetical_disruptions=hypothetical,
            occurrence_probability=0.5, assumptions=["Stub fixture"],
            rationale="Selects supplied temporal candidates and adds one advertised hypothetical.", metadata=metadata)
        return RiskGenerationResponse(proposals=[proposal], metadata=metadata)


class StubHypothesisProvider:
    """Generate bounded browser-local hypotheses from advertised client contracts."""

    async def propose_hypotheses(
        self, request: HypothesisGenerationRequest,
    ) -> HypothesisGenerationResponse:
        metadata = _metadata("hypothesis")
        if not request.disruption_contracts or not request.entity_scope:
            return HypothesisGenerationResponse(metadata=metadata)
        hypotheses = []
        contracts = sorted(request.disruption_contracts, key=lambda item: item.type)
        for index, contract in enumerate(contracts[:request.generation_limit], 1):
            valid_types = {item.casefold() for item in contract.target_types}
            target_ids = sorted(item.entity_id for item in request.entity_scope
                                if item.entity_type.casefold() in valid_types)
            if not target_ids:
                continue
            hypotheses.append(HypothesisSignalProposal(id=f"stub-hypothesis-{index}",
                name=f"Hypothesis {index}: {contract.type.replace('_', ' ').title()}",
                signal_type=contract.type,
                payload=_stub_value(contract.payload_schema, target_ids),
                occurrence_probability=max(0.1, 0.6 - (index - 1) * 0.1),
                rationale=f"Generated from the user prompt using advertised {contract.type} capability.",
                metadata=metadata))
        return HypothesisGenerationResponse(hypotheses=hypotheses, metadata=metadata)


class StubPlannerProvider:
    """Return alternatives using only advertised intervention capabilities."""

    async def propose_plans(self, request: PlannerRequest) -> PlannerResponse:
        _fixture_failure(request.fixture_marker)
        metadata = _metadata("planner")
        if request.fixture_marker == "empty" or request.proposal_limit == 0 or not request.intervention_contracts:
            return PlannerResponse(metadata=metadata)
        scoped = {item.entity_id: item.entity_type.casefold() for item in request.entity_scope}
        eligible = [(contract, sorted(entity_id for entity_id, entity_type in scoped.items()
                    if entity_type in {kind.casefold() for kind in contract.target_types}))
                    for contract in sorted(request.intervention_contracts, key=lambda item: item.type)]
        contract, target_ids = next(((contract, ids) for contract, ids in eligible if ids),
                                    (sorted(request.intervention_contracts, key=lambda item: item.type)[0],
                                     request.known_entity_ids))
        count = min(request.proposal_limit, 2 if request.fixture_marker == "multiple" else 1)
        proposals = [PlanProposal(proposal_id=f"stub-plan-{index + 1}",
            name=f"Deterministic intervention {index + 1}",
            interventions=[ProposedIntervention(type=contract.type,
                payload=_stub_value(contract.payload_schema, target_ids))],
            rationale="Uses an advertised intervention capability.", assumptions=["Stub fixture"],
            expected_qualitative_effects=["May improve the selected objective"], metadata=metadata)
            for index in range(count)]
        return PlannerResponse(proposals=proposals, metadata=metadata)


class StubPlannerPanelProvider:
    """Bounded deterministic role panel implementing the existing planner protocol."""

    roles = (
        ("continuity", "Prioritize operational continuity and service recovery."),
        ("cost", "Prioritize resource efficiency and cost control."),
        ("resilience", "Prioritize robust mitigation under uncertainty."),
        ("responsiveness", "Prioritize speed of implementation and near-term risk reduction."),
        ("sustainability", "Prioritize durable and environmentally responsible mitigation."),
    )

    def __init__(self, agent_count: int = 3) -> None:
        if not 1 <= agent_count <= 5:
            raise ValueError("Panel agent count must be between 1 and 5")
        self._agent_count = agent_count

    async def propose_plans(self, request: PlannerRequest) -> PlannerResponse:
        _fixture_failure(request.fixture_marker)
        metadata = _metadata("planner-panel")
        if request.fixture_marker == "empty" or request.proposal_limit == 0 or not request.intervention_contracts:
            return PlannerResponse(metadata=metadata)
        scoped = {item.entity_id: item.entity_type.casefold() for item in request.entity_scope}
        eligible = [(contract, sorted(entity_id for entity_id, entity_type in scoped.items()
                    if entity_type in {kind.casefold() for kind in contract.target_types}))
                    for contract in sorted(request.intervention_contracts, key=lambda item: item.type)]
        contract, target_ids = next(((contract, ids) for contract, ids in eligible if ids),
                                    (sorted(request.intervention_contracts, key=lambda item: item.type)[0],
                                     request.known_entity_ids))
        proposals = []
        limit = min(request.proposal_limit, self._agent_count)
        for index, (role, rationale) in enumerate(self.roles[:limit], 1):
            role_metadata = ProviderMetadata(provider="stub-panel",
                model=f"deterministic-{role}-planner", prompt_version="panel-v1", stub=True)
            proposals.append(PlanProposal(proposal_id=f"stub-panel-{role}",
                name=f"{role.title()} planner proposal",
                interventions=[ProposedIntervention(type=contract.type,
                    payload=_stub_value(contract.payload_schema, target_ids))],
                rationale=rationale, assumptions=["Deterministic stub panel"],
                expected_qualitative_effects=["Requires authoritative simulation"],
                metadata=role_metadata))
        return PlannerResponse(proposals=proposals, metadata=metadata)


@dataclass(frozen=True)
class ProviderBundle:
    """Collect the purpose-specific providers used by signal workflows."""

    filter: FilterProvider
    interpreter: InterpreterProvider
    effect_mapping: EffectMappingProvider
    relationship: RelationshipProvider
