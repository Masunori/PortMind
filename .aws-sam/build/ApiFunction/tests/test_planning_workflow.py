"""Risk/planning contract, determinism, lifecycle, and trust-boundary tests."""

import asyncio
import pytest
from pydantic import ValidationError
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from app.domain.plan import PlanningLifecycle
from app.integrations.contracts import (
    PlannerRequest, RiskGenerationRequest, SimulationResults, SimulationStatus,
    DisruptionApplicationStatus, DisruptionReconciliationResponse,
    ReconciledDisruption, RiskGenerationResponse, RiskScenarioProposal,
    ProviderMetadata, EntityCandidate, EvidenceCreate, EvidenceKind,
    HypothesisGenerationRequest, HypothesisGenerationResponse, HypothesisSignalProposal,
    GenerationEntity,
    EntitySearchResponse,
)
from app.integrations.factory import get_planner_provider, get_risk_provider
from app.integrations.errors import ClientGatewayError
from app.integrations.providers import (
    StubHypothesisProvider, StubPlannerPanelProvider, StubPlannerProvider, StubRiskProvider,
)
from app.services.planning_service import PlanningService, get_cycle, save_cycle
from app.api import planning as planning_api
from tests.fakes import FakeClientGateway
from app.domain.source import DataSourceCreate, SourceType
from app.integrations.providers import ProviderBundle, StubEffectMappingProvider, StubFilterProvider, StubInterpreterProvider, StubRelationshipProvider
from app.models import SignalVersionRecord
from app.services.evidence_service import store_evidence
from app.services.signal_service import process_evidence, review_signal
from app.services.source_service import create_source


def run(value): return asyncio.run(value)


def entity(entity_id="entity-1", entity_type="PORT", name="Entity One"):
    return GenerationEntity(entity_id=entity_id, entity_type=entity_type, display_name=name)


def risk_request(gateway, **changes):
    context = run(gateway.get_context()); catalog = run(gateway.get_disruption_contracts())
    values = dict(context_summary={}, context_version=context.context_version,
        state_version=context.state_version, disruption_contracts=catalog.contracts,
        entity_scope=[entity()])
    values.update(changes)
    return RiskGenerationRequest(**values)


def planner_request(gateway, **changes):
    context = run(gateway.get_context()); catalog = run(gateway.get_intervention_contracts())
    values = dict(planning_cycle_id="cycle-1", scenario_id="scenario-1",
        context_version=context.context_version, state_version=context.state_version,
        disruptions=[], baseline_run_id="baseline-1", baseline_results={"late_shipments": 5},
        intervention_contracts=catalog.contracts, known_entity_ids=["entity-1"])
    values.update(changes)
    return PlannerRequest(**values)


def test_contracts_forbid_extras_and_agent_metrics():
    gateway = FakeClientGateway()
    values = planner_request(gateway).model_dump(); values["secret"] = True
    with pytest.raises(ValidationError): PlannerRequest.model_validate(values)
    proposal = run(StubPlannerProvider().propose_plans(planner_request(gateway))).proposals[0]
    raw = proposal.model_dump(); raw["predicted_metrics"] = {"late_shipments": 0}
    with pytest.raises(ValidationError): type(proposal).model_validate(raw)


@pytest.mark.parametrize("provider,provider_request,method", [
    (StubRiskProvider(), risk_request(FakeClientGateway()), "propose_scenarios"),
    (StubPlannerProvider(), planner_request(FakeClientGateway()), "propose_plans"),
])
def test_stubs_are_deterministic_and_keep_known_ids(provider, provider_request, method):
    first = run(getattr(provider, method)(provider_request)); second = run(getattr(provider, method)(provider_request))
    assert first == second
    payloads = [item.payload for proposal in first.proposals for item in
                (proposal.hypothetical_disruptions
                 if hasattr(proposal, "hypothetical_disruptions") else proposal.interventions)]
    assert all(set(payload.get("target_ids", [])) <= {"entity-1"} for payload in payloads)


def test_risk_stub_supports_nullable_schema_and_produces_an_ordered_window():
    proposal = run(StubRiskProvider().propose_scenarios(
        risk_request(FakeClientGateway()))).proposals[0]
    payload = proposal.hypothetical_disruptions[0].payload
    assert payload["effective_until"] is not None
    assert payload["effective_from"] < payload["effective_until"]


@pytest.mark.parametrize("marker,error", [("timeout", TimeoutError), ("failure", RuntimeError),
                                            ("malformed", ValueError)])
def test_provider_fixture_failures_are_explicit(marker, error):
    with pytest.raises(error):
        run(StubPlannerProvider().propose_plans(planner_request(FakeClientGateway(), fixture_marker=marker)))


def test_empty_and_multiple_proposals_from_the_single_planner():
    gateway = FakeClientGateway(); provider = StubPlannerProvider()
    assert run(provider.propose_plans(planner_request(gateway, fixture_marker="empty"))).proposals == []
    assert len(run(provider.propose_plans(planner_request(
        gateway, fixture_marker="multiple"))).proposals) == 2


def test_stub_hypothesis_provider_is_bounded_and_uses_known_ids():
    gateway = FakeClientGateway(); context = run(gateway.get_context())
    catalog = run(gateway.get_disruption_contracts())
    response = run(StubHypothesisProvider().propose_hypotheses(HypothesisGenerationRequest(
        prompt="What could increase lead time?", context_summary={},
        context_version=context.context_version, disruption_contracts=catalog.contracts,
        entity_scope=[entity()], generation_limit=2)))
    assert 1 <= len(response.hypotheses) <= 2
    assert response.hypotheses[0].classification == "HYPOTHETICAL"
    assert response.hypotheses[0].payload["target_ids"] == ["entity-1"]


def test_stub_planner_panel_returns_role_labelled_bounded_drafts():
    response = run(StubPlannerPanelProvider().propose_plans(
        planner_request(FakeClientGateway(), proposal_limit=2)))
    assert [item.proposal_id for item in response.proposals] == [
        "stub-panel-continuity", "stub-panel-cost"]
    assert all(item.metadata.provider == "stub-panel" for item in response.proposals)


def test_factory_rejects_unknown_single_provider_configuration(monkeypatch):
    assert isinstance(get_risk_provider(), StubRiskProvider)
    assert isinstance(get_planner_provider(), StubPlannerProvider)
    monkeypatch.setenv("PLANNER_PROVIDER", "panel")
    with pytest.raises(ValueError, match="PLANNER_PROVIDER=panel"): get_planner_provider()


def completed_gateway(result=None):
    return FakeClientGateway(status=SimulationStatus(run_id="fake-run-1", status="COMPLETED"),
        results=SimulationResults(run_id="fake-run-1", context_version="context-v1",
            state_version="state-v1", result=result or {"late_shipments": 10,
                "average_delay": 3, "total_cost": 100}, completed_at="2025-01-01T00:00:00Z"))


def accepted_forecast(gateway):
    bundle = ProviderBundle(filter=StubFilterProvider(), interpreter=StubInterpreterProvider(),
        effect_mapping=StubEffectMappingProvider(), relationship=StubRelationshipProvider())
    source = create_source(DataSourceCreate(name="Risk reports", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.UPLOAD,
        title="Port forecast", media_type="text/plain", content="Hai Phong port may close"))
    signal = run(process_evidence(evidence.id, gateway=gateway, providers=bundle))
    review_signal(signal.signal_id, "ACCEPTED")
    return signal


class SelectingRiskProvider:
    def __init__(self): self.request = None

    async def propose_scenarios(self, request):
        self.request = request
        metadata = ProviderMetadata(provider="test", model="selector", prompt_version="v1")
        return RiskGenerationResponse(proposals=[RiskScenarioProposal(proposal_id="selected",
            name="Selected stored risk", selected_signal_version_ids=[item.signal_version_id
                for item in request.candidate_signals], occurrence_probability=0.8,
            rationale="Select every temporal candidate.", metadata=metadata)], metadata=metadata)


class EmptyRiskProvider:
    async def propose_scenarios(self, request):
        return RiskGenerationResponse(metadata=ProviderMetadata(
            provider="test", model="empty", prompt_version="v1"))


class FixedHypothesisProvider:
    def __init__(self, target_id="entity-1"):
        self.target_id = target_id
        self.request = None

    async def propose_hypotheses(self, request):
        self.request = request
        metadata = ProviderMetadata(provider="test", model="fixed", prompt_version="v1")
        return HypothesisGenerationResponse(hypotheses=[
            HypothesisSignalProposal(id="fixed-hypothesis", name="Fixed hypothesis",
                signal_type="PORT_CAPACITY_CHANGE", payload={"target_ids": [self.target_id],
                    "effective_from": "2026-09-01T00:00:00Z",
                    "effective_until": "2026-09-02T00:00:00Z",
                    "parameters": {"capacity_multiplier": 0.5}},
                occurrence_probability=0.5, rationale="Test fixture", metadata=metadata)],
            metadata=metadata)


class LikelihoodRiskProvider:
    async def propose_scenarios(self, request):
        metadata = ProviderMetadata(provider="test", model="likelihood", prompt_version="v1")
        contract = request.disruption_contracts[0]
        payload = {"target_ids": [item.entity_id for item in request.entity_scope[:1]],
            "effective_from": "2026-01-01T00:00:00Z",
            "effective_until": "2026-01-02T00:00:00Z",
            "parameters": {"capacity_multiplier": 0.5}}
        proposals = [RiskScenarioProposal(proposal_id=proposal_id, name=proposal_id,
            hypothetical_disruptions=[{"type": contract.type, "payload": payload}],
            occurrence_probability=probability, rationale="Likelihood fixture.",
            metadata=metadata) for proposal_id, probability in (("low", 0.2), ("high", 0.9))]
        return RiskGenerationResponse(proposals=proposals, metadata=metadata)


class StatusGateway(FakeClientGateway):
    def __init__(self, status):
        super().__init__(entities=[EntityCandidate(entity_id="hph", entity_type="port",
            display_name="Hai Phong", confidence=1)])
        self.application_status = status

    async def reconcile_disruptions(self, request):
        self._record("reconcile_disruptions", request)
        return DisruptionReconciliationResponse(context_version=request.context_version,
            state_version=request.state_version, catalog_version=request.catalog_version,
            disruptions=[ReconciledDisruption(disruption_id=item.disruption_id,
                application_status=self.application_status,
                normalized_disruption={"type": item.disruption_type, "payload": item.normalized_payload},
                reason_code="TEST_STATUS", classification=item.classification,
                source_signal_version_id=item.source_signal_version_id)
                for item in request.disruptions])


def test_risk_agent_selects_only_temporally_eligible_stored_references(test_session_factory):
    gateway = StatusGateway(DisruptionApplicationStatus.APPLY_IN_SIMULATION)
    signal = accepted_forecast(gateway); provider = SelectingRiskProvider()
    service = PlanningService(provider, StubPlannerProvider())
    scenario = run(service.generate_scenarios(gateway=gateway,
        planning_starts_at=signal.temporal_window.starts_at - timedelta(hours=1),
        planning_ends_at=signal.temporal_window.ends_at + timedelta(hours=1)))[0]
    assert [item.signal_version_id for item in provider.request.candidate_signals] == [signal.id]
    assert scenario.signal_version_ids == [signal.id]
    assert scenario.disruptions[0]["classification"] == "FORECAST"
    assert scenario.disruptions[0]["source_signal_version_id"] == signal.id


def test_temporally_ineligible_signal_is_not_exposed_to_risk_agent(test_session_factory):
    gateway = StatusGateway(DisruptionApplicationStatus.APPLY_IN_SIMULATION)
    signal = accepted_forecast(gateway); provider = SelectingRiskProvider()
    with pytest.raises(ValidationError, match="select or propose"):
        run(PlanningService(provider, StubPlannerProvider()).generate_scenarios(gateway=gateway,
            planning_starts_at=signal.temporal_window.ends_at + timedelta(days=1),
            planning_ends_at=signal.temporal_window.ends_at + timedelta(days=2)))
    assert provider.request.candidate_signals == []


def test_already_reflected_disruption_stays_in_scenario_but_not_active_inputs(test_session_factory):
    gateway = StatusGateway(DisruptionApplicationStatus.ALREADY_REFLECTED)
    signal = accepted_forecast(gateway); provider = SelectingRiskProvider()
    service = PlanningService(provider, StubPlannerProvider())
    scenario = run(service.generate_scenarios(gateway=gateway,
        planning_starts_at=signal.temporal_window.starts_at - timedelta(hours=1),
        planning_ends_at=signal.temporal_window.ends_at + timedelta(hours=1)))[0]
    assert len(scenario.disruptions) == 1
    assert scenario.disruptions[0]["application_status"] == "ALREADY_REFLECTED"
    assert scenario.active_disruptions == []
    run(service.start_cycle(scenario, gateway=gateway))
    submission = next(request for name, request in gateway.calls if name == "submit_simulation")
    assert submission.scenario_disruptions == scenario.disruptions
    assert submission.active_disruptions == []


def test_unknown_reflection_status_stops_before_simulation(test_session_factory):
    gateway = StatusGateway(DisruptionApplicationStatus.UNKNOWN)
    signal = accepted_forecast(gateway); provider = SelectingRiskProvider()
    with pytest.raises(ValueError, match="already reflected"):
        run(PlanningService(provider, StubPlannerProvider()).generate_scenarios(gateway=gateway,
            planning_starts_at=signal.temporal_window.starts_at - timedelta(hours=1),
            planning_ends_at=signal.temporal_window.ends_at + timedelta(hours=1)))
    assert not any(name == "submit_simulation" for name, _ in gateway.calls)


def test_generated_scenarios_are_ranked_by_likelihood(test_session_factory):
    gateway = StatusGateway(DisruptionApplicationStatus.APPLY_IN_SIMULATION)
    signal = accepted_forecast(gateway)
    scenarios = run(PlanningService(LikelihoodRiskProvider(), StubPlannerProvider())
        .generate_scenarios(gateway=gateway,
            planning_starts_at=signal.temporal_window.starts_at - timedelta(hours=1),
            planning_ends_at=signal.temporal_window.ends_at + timedelta(hours=1)))
    assert [item.proposal_id for item in scenarios] == ["high", "low"]


def test_end_to_end_single_planner_flow_uses_frozen_scenario_and_authoritative_metrics(test_session_factory):
    gateway = completed_gateway(); service = PlanningService(StubRiskProvider(), StubPlannerProvider())
    scenarios = run(service.generate_scenarios(gateway=gateway, entity_scope=[entity()]))
    cycle = run(service.start_cycle(scenarios[0], gateway=gateway))
    assert cycle.baseline_metrics["late_shipments"] == 10
    cycle = run(service.propose_plans(cycle, gateway=gateway,
        known_entity_ids=["entity-1"], fixture_marker="multiple"))
    assert len(cycle.plans) == 2
    cycle = run(service.submit_plan(cycle, cycle.plans[0].id, gateway=gateway))
    baseline, intervention = [request for name, request in gateway.calls if name == "submit_simulation"]
    assert baseline.disruptions == intervention.disruptions
    assert baseline.context_version == intervention.context_version
    assert intervention.provenance["baseline_run_id"] == cycle.baseline_run_id
    cycle = service.rank(cycle)
    assert cycle.plans[0].status == PlanningLifecycle.RECOMMENDED
    with pytest.raises(ValueError): service.decide(
        cycle.model_copy(update={"plans": [cycle.plans[1]]}), cycle.plans[1].id,
        PlanningLifecycle.APPROVED)
    decided = service.decide(cycle, cycle.plans[0].id, PlanningLifecycle.APPROVED)
    assert decided.status == PlanningLifecycle.APPROVED
    save_cycle(decided)
    assert get_cycle(decided.id) == decided


def test_planner_is_not_called_before_completed_baseline(test_session_factory):
    gateway = FakeClientGateway(status=SimulationStatus(run_id="fake-run-1", status="RUNNING"))
    service = PlanningService(StubRiskProvider(), StubPlannerProvider())
    scenario = run(service.generate_scenarios(gateway=gateway, entity_scope=[entity()]))[0]
    cycle = run(service.start_cycle(scenario, gateway=gateway))
    with pytest.raises(ValueError, match="completed baseline"):
        run(service.propose_plans(cycle, gateway=gateway))
    assert not any(name == "get_intervention_contracts" for name, _ in gateway.calls)


def test_unknown_targets_and_invalid_interventions_are_rejected(test_session_factory):
    gateway = completed_gateway(); service = PlanningService(StubRiskProvider(), StubPlannerProvider())
    scenario = run(service.generate_scenarios(gateway=gateway, entity_scope=[entity()]))[0]
    cycle = run(service.start_cycle(scenario, gateway=gateway))
    from app.integrations.contracts import InterventionValidationResponse
    gateway.responses["intervention_validation"] = InterventionValidationResponse(valid=False,
        errors=["unsupported target"], catalog_version="interventions-v1", context_version="context-v1")
    with pytest.raises(ValueError, match="Client rejected intervention"):
        run(service.propose_plans(cycle, gateway=gateway, known_entity_ids=["entity-1"]))


def test_ranking_is_stable_and_excludes_failed_or_missing_metrics(test_session_factory):
    gateway = completed_gateway(); service = PlanningService(StubRiskProvider(), StubPlannerProvider())
    scenario = run(service.generate_scenarios(gateway=gateway, entity_scope=[entity()]))[0]
    cycle = run(service.start_cycle(scenario, gateway=gateway))
    cycle = run(service.propose_plans(cycle, gateway=gateway,
        known_entity_ids=["entity-1"], fixture_marker="multiple"))
    plans = [item.model_copy(update={"status": PlanningLifecycle.EVALUATED,
        "intervention_metrics": {"late_shipments": 1, "average_delay": 2, "total_cost": 3}})
        for item in cycle.plans]
    ranked = service.rank(cycle.model_copy(update={"plans": list(reversed(plans))}))
    winner = next(item for item in ranked.plans if item.status == PlanningLifecycle.RECOMMENDED)
    assert winner.proposal_id == "stub-plan-1"
    assert ranked.ranking_policy_version == "lexicographic-v1"


def test_generation_creates_review_draft_without_submitting_simulation(test_session_factory):
    gateway = FakeClientGateway(); service = PlanningService(StubRiskProvider(), StubPlannerProvider())
    draft = run(service.create_draft(gateway=gateway, entity_scope=[entity()]))
    assert draft.status == PlanningLifecycle.PROPOSED
    assert draft.generated_scenarios
    assert draft.selected_disruption_ids
    assert draft.baseline_run_id is None
    assert not any(name == "submit_simulation" for name, _ in gateway.calls)


def test_user_can_remove_generated_disruption_before_explicit_baseline(test_session_factory):
    gateway = StatusGateway(DisruptionApplicationStatus.APPLY_IN_SIMULATION)
    accepted_forecast(gateway)
    service = PlanningService(StubRiskProvider(), StubPlannerProvider())
    draft = run(service.create_draft(gateway=gateway, entity_scope=[entity()]))
    assert len(draft.selected_disruption_ids) == 2
    reviewed = service.compose_scenario(draft, [draft.selected_disruption_ids[0]])
    assert len(reviewed.scenario.disruptions) == 1
    assert reviewed.baseline_run_id is None
    submitted = run(service.submit_baseline(reviewed, gateway=gateway))
    request = [request for name, request in gateway.calls if name == "submit_simulation"][-1]
    assert request.scenario_disruptions == reviewed.scenario.disruptions
    assert submitted.baseline_metrics is not None


def test_review_rejects_empty_unknown_and_post_submission_edits(test_session_factory):
    gateway = FakeClientGateway(); service = PlanningService(StubRiskProvider(), StubPlannerProvider())
    draft = run(service.create_draft(gateway=gateway, entity_scope=[entity()]))
    with pytest.raises(ValueError, match="at least one"): service.compose_scenario(draft, [])
    with pytest.raises(ValueError, match="unknown disruption"): service.compose_scenario(draft, ["missing"])
    submitted = run(service.submit_baseline(draft, gateway=gateway))
    with pytest.raises(ValueError, match="no longer be edited"):
        service.compose_scenario(submitted, draft.selected_disruption_ids)


def test_completed_baseline_results_are_the_planner_input(test_session_factory):
    class CapturingPlanner(StubPlannerProvider):
        def __init__(self): self.requests = []

        async def propose_plans(self, request):
            self.requests.append(request)
            return await super().propose_plans(request)

    gateway = completed_gateway(); planner = CapturingPlanner()
    service = PlanningService(StubRiskProvider(), planner)
    draft = run(service.create_draft(gateway=gateway, entity_scope=[entity()]))
    completed = run(service.submit_baseline(draft, gateway=gateway))
    planned = run(planning_api._propose_after_result(completed, planner=service, gateway=gateway))
    repeated = run(planning_api._propose_after_result(planned, planner=service, gateway=gateway))
    assert completed.baseline_metrics == {"late_shipments": 10, "average_delay": 3, "total_cost": 100}
    assert planned.plans
    assert repeated == planned
    assert len(planner.requests) == 1
    assert planner.requests[0].baseline_results == completed.baseline_metrics
    assert planner.requests[0].known_entity_ids == ["entity-1"]


def test_completed_baseline_survives_unavailable_automatic_plan_generation(test_session_factory):
    class MissingInterventionCatalogGateway(FakeClientGateway):
        async def get_intervention_contracts(self):
            raise ClientGatewayError(
                "Client rejected GET /intervention-contracts with status 404")

    gateway = MissingInterventionCatalogGateway(
        status=SimulationStatus(run_id="fake-run-1", status="COMPLETED"),
        results=SimulationResults(run_id="fake-run-1", context_version="context-v1",
            state_version="state-v1", result={"late_shipments": 10},
            completed_at=datetime.now(timezone.utc)))
    planner = PlanningService(StubRiskProvider(), StubPlannerProvider())
    cycle = run(planner.submit_baseline(run(planner.create_draft(
        gateway=gateway, entity_scope=[entity()])), gateway=gateway))

    result = run(planning_api._propose_after_result(cycle, planner=planner, gateway=gateway))

    assert result.baseline_metrics == {"late_shipments": 10}
    assert result.plans == []
    assert result.error_code == "CLIENT_ERROR"
    assert "GET /intervention-contracts" in result.error_message


def test_validated_proposal_can_be_rejected_but_not_approved(test_session_factory):
    gateway = completed_gateway(); service = PlanningService(StubRiskProvider(), StubPlannerProvider())
    cycle = run(service.submit_baseline(run(service.create_draft(
        gateway=gateway, entity_scope=[entity()])), gateway=gateway))
    cycle = run(service.propose_plans(cycle, gateway=gateway, known_entity_ids=[]))
    with pytest.raises(ValueError, match="recommendation"):
        service.decide(cycle, cycle.plans[0].id, PlanningLifecycle.APPROVED)
    rejected = service.decide(cycle, cycle.plans[0].id, PlanningLifecycle.REJECTED)
    assert rejected.plans[0].status == PlanningLifecycle.REJECTED


def test_planning_api_generates_reviews_runs_and_auto_proposes(test_session_factory):
    gateway = completed_gateway()
    draft = run(planning_api.create_cycle(planning_api.CycleCreate(
        generation_limit=5, entity_scope=[entity()]), gateway))
    assert draft.status == PlanningLifecycle.PROPOSED
    assert not any(name == "submit_simulation" for name, _ in gateway.calls)
    reviewed = planning_api.select_scenario(draft.id, planning_api.ScenarioSelection(
        disruption_ids=draft.selected_disruption_ids[:1]))
    completed = run(planning_api.submit_baseline(reviewed.id, gateway))
    assert completed.baseline_metrics is not None
    assert completed.plans
    assert completed.status == PlanningLifecycle.RECOMMENDED
    assert all(item.intervention_run_id for item in completed.plans)
    assert sum(name == "submit_simulation" for name, _ in gateway.calls) == 1 + len(completed.plans)
    assert get_cycle(draft.id) == completed


def test_confirmed_browser_hypothesis_enters_draft_but_not_signal_database(test_session_factory):
    gateway = StatusGateway(DisruptionApplicationStatus.APPLY_IN_SIMULATION)
    signal = accepted_forecast(gateway)
    catalog = run(gateway.get_disruption_contracts())
    generated = run(StubHypothesisProvider().propose_hypotheses(HypothesisGenerationRequest(
        prompt="What if port capacity falls?", context_summary={}, context_version="context-v1",
        disruption_contracts=catalog.contracts,
        entity_scope=[entity("hph", "PORT", "Hai Phong")], generation_limit=1)))
    service = PlanningService(SelectingRiskProvider(), StubPlannerProvider())
    draft = run(service.create_draft(gateway=gateway,
        planning_starts_at=signal.temporal_window.starts_at - timedelta(hours=1),
        planning_ends_at=signal.temporal_window.ends_at + timedelta(hours=1),
        confirmed_hypotheses=generated.hypotheses))
    assert any(item["classification"] == "HYPOTHETICAL"
               for scenario in draft.generated_scenarios for item in scenario.disruptions)
    with test_session_factory() as session:
        assert session.scalar(select(SignalVersionRecord).where(
            SignalVersionRecord.classification == "HYPOTHETICAL")) is None


def test_panel_mode_is_persisted_and_auto_generates_panel_plans(test_session_factory):
    gateway = completed_gateway()
    draft = run(planning_api.create_cycle(planning_api.CycleCreate(
        generation_limit=5, planner_mode="panel", objectives=["protect service"],
        hard_constraints={"total_cost": 200}, entity_scope=[entity()]), gateway))
    completed = run(planning_api.submit_baseline(draft.id, gateway))
    assert completed.planner_mode == "panel"
    assert {item.planner_metadata["provider"] for item in completed.plans} == {"stub-panel"}
    assert len(completed.plans) == 3
    assert completed.status == PlanningLifecycle.RECOMMENDED
    assert sorted(item.rank for item in completed.plans) == [1, 2, 3]
    assert completed.planning_objectives == ["protect service"]
    assert completed.hard_constraints == {"total_cost": 200}


def test_panel_agent_count_is_persisted_and_bounds_generated_plans(test_session_factory):
    gateway = completed_gateway()
    draft = run(planning_api.create_cycle(planning_api.CycleCreate(
        generation_limit=5, planner_mode="panel", panel_agent_count=5,
        entity_scope=[entity()]), gateway))
    completed = run(planning_api.submit_baseline(draft.id, gateway))
    assert completed.panel_agent_count == 5
    assert len(completed.plans) == 5


@pytest.mark.parametrize("count", [0, 6])
def test_panel_agent_count_must_be_between_one_and_five(count):
    with pytest.raises(ValidationError):
        planning_api.CycleCreate(planner_mode="panel", panel_agent_count=count)


def test_hypothesis_api_returns_reviewable_proposals_without_persistence(test_session_factory):
    gateway = FakeClientGateway()
    response = run(planning_api.generate_hypotheses(
        planning_api.HypothesisGenerationBody(prompt="lead-time risks",
            entity_scope=[entity()], generation_limit=2),
        gateway, StubHypothesisProvider()))
    assert response.hypotheses
    with test_session_factory() as session:
        assert session.scalar(select(SignalVersionRecord)) is None


def test_hypothesis_api_supplies_named_typed_entity_scope_to_provider(test_session_factory):
    provider = FixedHypothesisProvider()
    scope = [entity("entity-1", "PORT", "Port of Singapore")]
    response = run(planning_api.generate_hypotheses(
        planning_api.HypothesisGenerationBody(prompt="port risks", entity_scope=scope),
        FakeClientGateway(), provider))
    assert response.hypotheses[0].payload["target_ids"] == ["entity-1"]
    assert provider.request.entity_scope == scope


def test_generation_entity_search_returns_authoritative_structured_candidates():
    gateway = FakeClientGateway(entities=[EntityCandidate(entity_id="port-sg",
        entity_type="PORT", display_name="Port of Singapore", confidence=0.9)])
    results = run(planning_api.search_generation_entities(
        planning_api.GenerationEntitySearchBody(query="Singapore", entity_types=["PORT"]),
        gateway))
    assert results == [entity("port-sg", "PORT", "Port of Singapore")]
    request = next(value for name, value in gateway.calls if name == "search_entities")
    assert request.entity_types == ["PORT"]
    assert request.context_version == "context-v1"


def test_generation_entity_search_rejects_stale_client_context():
    gateway = FakeClientGateway(search=EntitySearchResponse(
        candidates=[], context_version="stale-context"))
    with pytest.raises(planning_api.HTTPException) as error:
        run(planning_api.search_generation_entities(
            planning_api.GenerationEntitySearchBody(query="port"), gateway))
    assert error.value.status_code == 422
    assert "stale context" in str(error.value.detail)


def test_hypothesis_api_rejects_entity_type_incompatible_with_contract(test_session_factory):
    with pytest.raises(planning_api.HTTPException) as error:
        run(planning_api.generate_hypotheses(
            planning_api.HypothesisGenerationBody(prompt="port risks",
                entity_scope=[entity("entity-1", "VESSEL", "Vessel One")]),
            FakeClientGateway(), FixedHypothesisProvider()))
    assert error.value.status_code == 422
    assert "incompatible entity type" in str(error.value.detail)


def test_confirmed_hypothesis_keeps_explicit_scope_without_eligible_signal(test_session_factory):
    gateway = FakeClientGateway()
    metadata = ProviderMetadata(provider="test", model="human", prompt_version="v1")
    hypothesis = HypothesisSignalProposal(id="hyp-port", name="Port capacity",
        signal_type="PORT_CAPACITY_CHANGE", payload={"target_ids": ["port-sg"],
            "effective_from": "2026-09-01T00:00:00Z",
            "effective_until": "2026-09-02T00:00:00Z",
            "parameters": {"capacity_multiplier": 0.5}}, occurrence_probability=0.4,
        rationale="Human-confirmed scenario", metadata=metadata)
    draft = run(PlanningService(EmptyRiskProvider(), StubPlannerProvider()).create_draft(
        gateway=gateway, confirmed_hypotheses=[hypothesis],
        entity_scope=[entity("port-sg", "PORT", "Port of Singapore")]))
    assert draft.scenario.disruptions[0]["payload"]["target_ids"] == ["port-sg"]


def test_conflicting_entity_types_for_same_id_are_rejected(test_session_factory):
    with pytest.raises(ValueError, match="conflicting types"):
        run(PlanningService(EmptyRiskProvider(), StubPlannerProvider()).generate_scenarios(
            gateway=FakeClientGateway(), entity_scope=[
                entity("shared", "PORT", "Port"), entity("shared", "VESSEL", "Vessel")]))
