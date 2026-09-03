"""Deterministic orchestration around one risk and one planner provider."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.domain.plan import FrozenScenario, PlanRecordView, PlanningCycle, PlanningLifecycle
from app.integrations.contracts import (
    DisruptionValidationRequest, InterventionValidationRequest, PlannerRequest,
    RiskGenerationRequest, RiskSignalCandidate, SignalClass, SimulationSubmission,
    TemporalWindow, DisruptionReconciliationItem, DisruptionReconciliationRequest,
    DisruptionApplicationStatus, HypothesisSignalProposal, ProposedDisruption,
    RiskScenarioProposal, GenerationEntity, EntitySearchRequest,
)
from app.integrations.gateway import ClientGateway
from app.integrations.errors import ClientContractError
from app.integrations.providers import PlannerProvider, RiskProvider
from app.integrations.schema_validation import admit_schema, validate_payload
from app.database import SessionLocal
from app.models import (
    PlanningCycleRecord, SignalEffectRecord, SignalEntityRecord, SignalRecord,
    SignalRelationshipRecord, SignalVersionRecord,
)


def _key(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest()


def _targets(payload: dict[str, Any]) -> set[str]:
    value = payload.get("target_ids", [])
    return set(value) if isinstance(value, list) else set()


def save_cycle(cycle: PlanningCycle) -> PlanningCycle:
    """Persist a workflow snapshot without treating copied metrics as authoritative input."""
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        record = session.get(PlanningCycleRecord, cycle.id)
        if record is None:
            record = PlanningCycleRecord(id=cycle.id, created_at=now, updated_at=now,
                                         status=cycle.status.value, payload={})
            session.add(record)
        record.status = cycle.status.value
        record.payload = cycle.model_dump(mode="json")
        record.updated_at = now
    return cycle


def get_cycle(cycle_id: str) -> PlanningCycle | None:
    with SessionLocal() as session:
        record = session.get(PlanningCycleRecord, cycle_id)
        return PlanningCycle.model_validate(record.payload) if record else None


def list_cycles() -> list[PlanningCycle]:
    with SessionLocal() as session:
        records = session.scalars(select(PlanningCycleRecord).order_by(PlanningCycleRecord.id)).all()
        return [PlanningCycle.model_validate(item.payload) for item in records]


def _window_overlaps(window: TemporalWindow, starts_at: datetime, ends_at: datetime) -> bool:
    window_end = _as_utc(window.ends_at) if window.ends_at else None
    window_start = _as_utc(window.starts_at) if window.starts_at else None
    return (window_end is None or window_end > starts_at) and (
        window_start is None or window_start < ends_at)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _load_risk_candidates(context_version: str, starts_at: datetime, ends_at: datetime):
    """Load eligible stored signals and their trusted normalized disruptions."""
    with SessionLocal() as session:
        versions = list(session.scalars(select(SignalVersionRecord).join(
            SignalRecord, SignalRecord.id == SignalVersionRecord.signal_id).where(
                SignalRecord.review_status == "ACCEPTED",
                SignalVersionRecord.processing_state == "READY_FOR_REVIEW",
                SignalVersionRecord.classification.in_(["OBSERVED", "FORECAST"]),
                SignalVersionRecord.context_version == context_version,
            ).order_by(SignalVersionRecord.id)))
        effects = {item.signal_version_id: item for item in session.scalars(select(
            SignalEffectRecord).where(SignalEffectRecord.signal_version_id.in_(
                [version.id for version in versions])))}
        entities: dict[str, list[str]] = {}
        for item in session.scalars(select(SignalEntityRecord).where(
                SignalEntityRecord.signal_version_id.in_([version.id for version in versions]))):
            if item.entity_id: entities.setdefault(item.signal_version_id, []).append(item.entity_id)
        relationships = list(session.scalars(select(SignalRelationshipRecord)))
    eligible = []
    for version in versions:
        window = TemporalWindow.model_validate(version.temporal_window)
        effect = effects.get(version.id)
        if effect and effect.normalized_disruption is not None and _window_overlaps(window, starts_at, ends_at):
            eligible.append((version, effect, window, sorted(set(entities.get(version.id, [])))))
    return eligible, relationships


def _validate_selected_relationships(selected: set[str], relationships: list[SignalRelationshipRecord]) -> None:
    for item in relationships:
        source = item.source_signal_version_id in selected
        target = item.target_signal_version_id in selected
        if item.relationship == "MUTUALLY_EXCLUSIVE" and source and target:
            raise ValueError("Risk provider selected mutually exclusive signals")
        if item.relationship == "REQUIRES" and source and not target:
            raise ValueError("Risk provider omitted a required signal")
        if item.relationship == "SUPERSEDES" and source and target:
            raise ValueError("Risk provider selected a superseded signal with its replacement")


def _merge_entity_scope(*groups: list[GenerationEntity]) -> list[GenerationEntity]:
    """Freeze one unambiguous entity description for each authoritative ID."""
    merged: dict[str, GenerationEntity] = {}
    for item in (entity for group in groups for entity in group):
        previous = merged.get(item.entity_id)
        if previous and previous.entity_type.casefold() != item.entity_type.casefold():
            raise ValueError(f"Entity scope has conflicting types for {item.entity_id}")
        # Later groups are more explicit; cycle-selected descriptions supersede
        # labels derived from stored signal mentions after type consistency is checked.
        merged[item.entity_id] = item
    return [merged[key] for key in sorted(merged)]


class PlanningService:
    """Validate all agent output and delegate every metric to ClientGateway."""

    def __init__(self, risk_provider: RiskProvider, planner_provider: PlannerProvider):
        self._risk_provider = risk_provider
        self._planner_provider = planner_provider

    async def generate_scenarios(self, *, gateway: ClientGateway,
            planning_starts_at: datetime | None = None, planning_ends_at: datetime | None = None,
            generation_limit: int = 5,
            confirmed_hypotheses: list[HypothesisSignalProposal] | None = None,
            entity_scope: list[GenerationEntity] | None = None,
            fixture_marker: str | None = None) -> list[FrozenScenario]:
        context = await gateway.get_context()
        catalog = await gateway.get_disruption_contracts()
        if catalog.context_version != context.context_version:
            raise ValueError("Disruption catalog context is stale")
        starts_at = _as_utc(planning_starts_at) if planning_starts_at else datetime.now(timezone.utc)
        ends_at = _as_utc(planning_ends_at) if planning_ends_at else starts_at + timedelta(days=30)
        if ends_at <= starts_at: raise ValueError("Planning horizon end must be after its start")
        eligible, relationships = _load_risk_candidates(context.context_version, starts_at, ends_at)
        eligible_ids = {entity_id for _, _, _, ids in eligible for entity_id in ids}
        eligible_version_ids = [version.id for version, _, _, _ in eligible]
        with SessionLocal() as session:
            grounded_scope = [GenerationEntity(entity_id=item.entity_id,
                entity_type=item.entity_type, display_name=item.mention)
                for item in session.scalars(select(SignalEntityRecord).where(
                    SignalEntityRecord.entity_id.in_(eligible_ids),
                    SignalEntityRecord.signal_version_id.in_(eligible_version_ids),
                    SignalEntityRecord.context_version == context.context_version))
                if item.entity_id and item.entity_type]
        frozen_scope = _merge_entity_scope(grounded_scope, entity_scope or [])
        candidates = [RiskSignalCandidate(signal_version_id=version.id,
            classification=SignalClass(version.classification), signal_type=version.signal_type,
            temporal_window=window, occurrence_probability=version.occurrence_probability,
            entity_ids=ids) for version, _, window, ids in eligible]
        request = RiskGenerationRequest(context_summary=context.compact_context,
            context_version=context.context_version, state_version=context.state_version,
            disruption_contracts=catalog.contracts, candidate_signals=candidates,
            entity_scope=frozen_scope, generation_limit=generation_limit,
            fixture_marker=fixture_marker)
        response = await self._risk_provider.propose_scenarios(request)
        proposals = list(response.proposals)
        confirmed = confirmed_hypotheses or []
        if confirmed:
            proposals.append(RiskScenarioProposal(proposal_id="human-confirmed-hypotheses",
                name="Human-confirmed hypotheses",
                description="Browser-local hypotheses confirmed for this planning cycle.",
                hypothetical_disruptions=[ProposedDisruption(type=item.signal_type,
                    payload=item.payload) for item in confirmed],
                occurrence_probability=max(item.occurrence_probability for item in confirmed),
                assumptions=["Confirmed by a human for scenario consideration"],
                rationale="Groups the hypotheses explicitly confirmed by the user.",
                metadata=response.metadata))
        scope_by_id = {item.entity_id: item for item in request.entity_scope}
        known = set(scope_by_id); contracts = {item.type: item for item in catalog.contracts}
        eligible_by_id = {version.id: (version, effect) for version, effect, _, _ in eligible}
        scenarios: list[FrozenScenario] = []
        seen: set[str] = set()
        for proposal in sorted(proposals, key=lambda item: item.proposal_id):
            selected = set(proposal.selected_signal_version_ids)
            if not selected.issubset(eligible_by_id):
                raise ValueError("Risk provider selected an unavailable signal version")
            _validate_selected_relationships(selected, relationships)
            combined: list[DisruptionReconciliationItem] = []
            for version_id in proposal.selected_signal_version_ids:
                version, effect = eligible_by_id[version_id]
                stored = effect.normalized_disruption
                combined.append(DisruptionReconciliationItem(disruption_id=f"signal:{version_id}",
                    classification=SignalClass(version.classification), disruption_type=stored["type"],
                    normalized_payload=stored["payload"], source_signal_version_id=version_id))
            hypothetical = proposal.hypothetical_disruptions
            if len(combined) + len(hypothetical) > 20:
                raise ValueError("A scenario cannot contain more than 20 disruptions")
            raw_keys = [_key({"type": item.disruption_type, "payload": item.normalized_payload}) for item in combined]
            raw_keys += [_key({"type": item.type, "payload": item.payload}) for item in hypothetical]
            if len(raw_keys) != len(set(raw_keys)): raise ValueError("Duplicate disruptions are not allowed")
            target_modes: dict[str, set[str]] = {}
            for item_type, payload in [(item.disruption_type, item.normalized_payload) for item in combined] + [
                    (item.type, item.payload) for item in hypothetical]:
                mode = "closed" if "clos" in item_type.casefold() else "delayed" if "delay" in item_type.casefold() else item_type
                for target in _targets(payload): target_modes.setdefault(target, set()).add(mode)
            if any({"closed", "delayed"} <= modes for modes in target_modes.values()):
                raise ValueError("A target cannot be both closed and delayed")
            for index, disruption in enumerate(hypothetical):
                contract = contracts.get(disruption.type)
                if contract is None: raise ValueError(f"Unknown disruption type: {disruption.type}")
                admit_schema(contract.payload_schema)
                errors = validate_payload(disruption.payload, contract.payload_schema)
                if errors: raise ValueError(f"Invalid disruption payload: {errors}")
                if not _targets(disruption.payload).issubset(known):
                    raise ValueError("Disruption references an unknown entity ID")
                if any(scope_by_id[target].entity_type.casefold() not in
                       {kind.casefold() for kind in contract.target_types}
                       for target in _targets(disruption.payload)):
                    raise ValueError("Disruption references an incompatible entity type")
                result = await gateway.validate_disruption(DisruptionValidationRequest(
                    disruption_type=disruption.type, payload=disruption.payload,
                    catalog_version=catalog.catalog_version, context_version=context.context_version,
                    schema_hash=contract.schema_hash))
                if not result.valid or result.normalized_payload is None:
                    raise ValueError(f"Client rejected disruption: {result.errors}")
                normalized = result.normalized_payload
                combined.append(DisruptionReconciliationItem(
                    disruption_id=f"hypothetical:{proposal.proposal_id}:{index}",
                    classification=SignalClass.HYPOTHETICAL,
                    disruption_type=normalized["type"], normalized_payload=normalized["payload"]))
            reconciliation = await gateway.reconcile_disruptions(DisruptionReconciliationRequest(
                context_version=context.context_version, state_version=context.state_version,
                catalog_version=catalog.catalog_version, disruptions=combined))
            if (reconciliation.context_version, reconciliation.state_version, reconciliation.catalog_version) != (
                    context.context_version, context.state_version, catalog.catalog_version):
                raise ValueError("Client reconciliation returned mismatched versions")
            expected = {item.disruption_id for item in combined}
            returned = [item.disruption_id for item in reconciliation.disruptions]
            if len(returned) != len(set(returned)) or set(returned) != expected:
                raise ValueError("Client reconciliation did not return every disruption exactly once")
            if any(item.application_status == DisruptionApplicationStatus.UNKNOWN
                   for item in reconciliation.disruptions):
                raise ValueError("Client could not determine whether a disruption is already reflected")
            source_by_id = {item.disruption_id: item for item in combined}
            reconciled = []
            active = []
            for item in sorted(reconciliation.disruptions, key=lambda value: value.disruption_id):
                source = source_by_id[item.disruption_id]
                entry = {**item.normalized_disruption,
                    "disruption_id": item.disruption_id,
                    "classification": source.classification.value,
                    "source_signal_version_id": source.source_signal_version_id,
                    "application_status": item.application_status.value,
                    "reason_code": item.reason_code}
                reconciled.append(entry)
                if item.application_status == DisruptionApplicationStatus.APPLY_IN_SIMULATION:
                    active.append(item.normalized_disruption)
            canonical = {"context": context.context_version, "state": context.state_version,
                         "disruptions": reconciled, "active": active, "proposal": proposal.proposal_id}
            identity = _key(canonical)
            if identity in seen: raise ValueError("Duplicate risk scenarios")
            seen.add(identity)
            scenarios.append(FrozenScenario(id=f"scenario-{identity[:24]}", proposal_id=proposal.proposal_id,
                name=proposal.name, context_version=context.context_version, state_version=context.state_version,
                disruptions=reconciled, active_disruptions=active,
                occurrence_probability=proposal.occurrence_probability,
                signal_version_ids=proposal.selected_signal_version_ids,
                provenance={"provider": proposal.metadata.model_dump(mode="json"),
                    "assumptions": proposal.assumptions, "rationale": proposal.rationale,
                    "planning_horizon": {"starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
                    "reconciliation_warnings": reconciliation.warnings}))
        return sorted(scenarios, key=lambda item: (-item.occurrence_probability, item.proposal_id))

    async def start_cycle(self, scenario: FrozenScenario, *, gateway: ClientGateway) -> PlanningCycle:
        context = await gateway.get_context()
        if (context.context_version, context.state_version) != (scenario.context_version, scenario.state_version):
            raise ValueError("STALE_STATE")
        cycle_id = f"cycle-{_key(scenario.model_dump(mode='json'))[:24]}"
        submission = SimulationSubmission(experiment_id=scenario.id,
            idempotency_key=_key({"baseline": scenario.model_dump(mode="json")}),
            context_version=scenario.context_version, state_version=scenario.state_version,
            signal_version_ids=scenario.signal_version_ids, disruptions=scenario.disruptions,
            scenario_disruptions=scenario.disruptions, active_disruptions=scenario.active_disruptions,
            occurrence_probability=scenario.occurrence_probability,
            provenance={"planning_cycle_id": cycle_id, "kind": "baseline"})
        accepted = await gateway.submit_simulation(submission)
        status = PlanningLifecycle.RUNNING if accepted.status in {"QUEUED", "RUNNING"} else (
            PlanningLifecycle.FAILED if accepted.status == "FAILED" else PlanningLifecycle.SUBMITTED)
        cycle = PlanningCycle(id=cycle_id, scenario=scenario, generated_scenarios=[scenario],
                              selected_disruption_ids=[item["disruption_id"]
                                  for item in scenario.disruptions], status=status,
                              baseline_run_id=accepted.run_id)
        return await self.refresh_baseline(cycle, gateway=gateway) if accepted.status == "COMPLETED" else cycle

    async def create_draft(self, *, gateway: ClientGateway,
            planning_starts_at: datetime | None = None, planning_ends_at: datetime | None = None,
            generation_limit: int = 5,
            confirmed_hypotheses: list[HypothesisSignalProposal] | None = None,
            entity_scope: list[GenerationEntity] | None = None,
            planner_mode: str = "single", panel_agent_count: int = 3,
            planning_objectives: list[str] | None = None,
            hard_constraints: dict[str, Any] | None = None,
            fixture_marker: str | None = None) -> PlanningCycle:
        """Generate and persist a reviewable scenario set without running a simulation."""
        generated = await self.generate_scenarios(gateway=gateway,
            planning_starts_at=planning_starts_at, planning_ends_at=planning_ends_at,
            generation_limit=generation_limit, confirmed_hypotheses=confirmed_hypotheses,
            entity_scope=entity_scope,
            fixture_marker=fixture_marker)
        if not generated:
            raise ValueError("Risk provider returned no scenarios")
        available_ids = []
        seen_payloads: set[str] = set()
        for scenario in generated:
            for item in scenario.disruptions:
                payload_key = _key({"type": item.get("type"), "payload": item.get("payload")})
                if payload_key not in seen_payloads:
                    available_ids.append(item["disruption_id"])
                    seen_payloads.add(payload_key)
        # The simulation contract admits at most 20 disruptions. Start with the first
        # deterministic page selected; every generated item remains available for review.
        selected = available_ids[:20]
        draft_id = f"cycle-{_key({'generated': [item.model_dump(mode='json') for item in generated], 'planner_mode': planner_mode, 'panel_agent_count': panel_agent_count})[:24]}"
        cycle = PlanningCycle(id=draft_id, scenario=generated[0], generated_scenarios=generated,
            selected_disruption_ids=selected, planner_mode=planner_mode,
            panel_agent_count=panel_agent_count,
            planning_objectives=planning_objectives or [],
            hard_constraints=hard_constraints or {},
            status=PlanningLifecycle.PROPOSED)
        return self.compose_scenario(cycle, selected)

    def compose_scenario(self, cycle: PlanningCycle,
                         selected_disruption_ids: list[str]) -> PlanningCycle:
        """Freeze a reviewed subset drawn only from client-reconciled proposals."""
        if cycle.baseline_run_id is not None:
            raise ValueError("A submitted scenario can no longer be edited")
        selected = list(dict.fromkeys(selected_disruption_ids))
        if not selected:
            raise ValueError("Select at least one disruption")
        if len(selected) > 20:
            raise ValueError("A scenario cannot contain more than 20 disruptions")
        generated = cycle.generated_scenarios or [cycle.scenario]
        available: dict[str, dict[str, Any]] = {}
        owners: dict[str, list[FrozenScenario]] = {}
        for scenario in generated:
            for disruption in scenario.disruptions:
                disruption_id = disruption["disruption_id"]
                if disruption_id in available and available[disruption_id] != disruption:
                    raise ValueError("Generated scenarios disagree on a disruption")
                available[disruption_id] = disruption
                owners.setdefault(disruption_id, []).append(scenario)
        unknown = set(selected) - set(available)
        if unknown:
            raise ValueError("Selection contains an unknown disruption ID")
        disruptions = [available[item] for item in selected]
        raw_keys = [_key({"type": item.get("type"), "payload": item.get("payload")})
                    for item in disruptions]
        if len(raw_keys) != len(set(raw_keys)):
            raise ValueError("Duplicate disruptions are not allowed")
        target_modes: dict[str, set[str]] = {}
        for item in disruptions:
            item_type = str(item.get("type", ""))
            mode = "closed" if "clos" in item_type.casefold() else (
                "delayed" if "delay" in item_type.casefold() else item_type)
            for target in _targets(item.get("payload", {})):
                target_modes.setdefault(target, set()).add(mode)
        if any({"closed", "delayed"} <= modes for modes in target_modes.values()):
            raise ValueError("A target cannot be both closed and delayed")
        signal_ids = list(dict.fromkeys(item.get("source_signal_version_id") for item in disruptions
                                       if item.get("source_signal_version_id")))
        with SessionLocal() as session:
            relationships = list(session.scalars(select(SignalRelationshipRecord)))
        _validate_selected_relationships(set(signal_ids), relationships)
        active = [{"type": item["type"], "payload": item["payload"]} for item in disruptions
                  if item.get("application_status") == DisruptionApplicationStatus.APPLY_IN_SIMULATION.value]
        contributing = {owner.id: owner for item in selected for owner in owners[item]}
        canonical = {"context": cycle.scenario.context_version,
            "state": cycle.scenario.state_version, "disruptions": disruptions, "active": active}
        identity = _key(canonical)
        scenario = FrozenScenario(id=f"scenario-{identity[:24]}", proposal_id="user-reviewed",
            name="Reviewed combined scenario", context_version=cycle.scenario.context_version,
            state_version=cycle.scenario.state_version, disruptions=disruptions,
            active_disruptions=active,
            occurrence_probability=max(item.occurrence_probability for item in contributing.values()),
            signal_version_ids=signal_ids, provenance={"composition": "user-reviewed",
                "source_scenario_ids": sorted(contributing),
                "probability_rule": "maximum contributing scenario probability"})
        return cycle.model_copy(update={"scenario": scenario,
            "selected_disruption_ids": selected, "status": PlanningLifecycle.PROPOSED,
            "plans": [], "baseline_metrics": None, "error_code": None, "error_message": None})

    async def submit_baseline(self, cycle: PlanningCycle, *, gateway: ClientGateway) -> PlanningCycle:
        """Submit the reviewed composition while preserving its generated alternatives."""
        if cycle.baseline_run_id is not None:
            raise ValueError("Baseline has already been submitted")
        context = await gateway.get_context()
        if (context.context_version, context.state_version) != (
                cycle.scenario.context_version, cycle.scenario.state_version):
            raise ValueError("STALE_STATE")
        submission = SimulationSubmission(experiment_id=cycle.scenario.id,
            idempotency_key=_key({"baseline": cycle.scenario.model_dump(mode="json")}),
            context_version=cycle.scenario.context_version,
            state_version=cycle.scenario.state_version,
            signal_version_ids=cycle.scenario.signal_version_ids,
            disruptions=cycle.scenario.disruptions,
            scenario_disruptions=cycle.scenario.disruptions,
            active_disruptions=cycle.scenario.active_disruptions,
            occurrence_probability=cycle.scenario.occurrence_probability,
            provenance={"planning_cycle_id": cycle.id, "kind": "baseline"})
        accepted = await gateway.submit_simulation(submission)
        status = PlanningLifecycle.RUNNING if accepted.status in {"QUEUED", "RUNNING"} else (
            PlanningLifecycle.FAILED if accepted.status == "FAILED" else PlanningLifecycle.SUBMITTED)
        updated = cycle.model_copy(update={"status": status, "baseline_run_id": accepted.run_id})
        return await self.refresh_baseline(updated, gateway=gateway) if accepted.status == "COMPLETED" else updated

    async def refresh_baseline(self, cycle: PlanningCycle, *, gateway: ClientGateway) -> PlanningCycle:
        if cycle.baseline_metrics is not None: return cycle
        if not cycle.baseline_run_id: raise ValueError("Baseline has not been submitted")
        status = await gateway.get_simulation(cycle.baseline_run_id)
        if status.status == "FAILED":
            return cycle.model_copy(update={"status": PlanningLifecycle.FAILED,
                "error_code": status.error_code or "SIMULATION_FAILED",
                "error_message": status.error_message or "Simulation failed"})
        if status.status != "COMPLETED":
            return cycle.model_copy(update={"status": PlanningLifecycle.RUNNING})
        results = await gateway.get_simulation_results(cycle.baseline_run_id,
            context_version=cycle.scenario.context_version, state_version=cycle.scenario.state_version,
            completed_at=status.updated_at)
        return cycle.model_copy(update={"status": PlanningLifecycle.VALIDATED,
                                        "baseline_metrics": results.result})

    async def propose_plans(self, cycle: PlanningCycle, *, gateway: ClientGateway,
            known_entity_ids: list[str] | None = None, objectives: list[str] | None = None,
            hard_constraints: dict[str, Any] | None = None, proposal_limit: int = 5,
            fixture_marker: str | None = None) -> PlanningCycle:
        if cycle.baseline_metrics is None or cycle.status == PlanningLifecycle.FAILED:
            raise ValueError("A completed baseline is required")
        catalog = await gateway.get_intervention_contracts()
        if catalog.context_version != cycle.scenario.context_version: raise ValueError("STALE_STATE")
        for contract in catalog.contracts:
            try:
                admit_schema(contract.payload_schema)
            except ClientContractError as error:
                raise ClientContractError(
                    f"Invalid intervention schema for {contract.type}: {error}") from error
        intervention_scope: list[GenerationEntity] = []
        if known_entity_ids is None:
            searches: dict[tuple[str, ...], list[GenerationEntity]] = {}
            for contract in catalog.contracts:
                target_types = tuple(sorted(set(contract.target_types)))
                if target_types not in searches:
                    response = await gateway.search_entities(EntitySearchRequest(
                        query="", entity_types=list(target_types),
                        context_version=catalog.context_version, limit=50))
                    if response.context_version != catalog.context_version:
                        raise ValueError("STALE_STATE")
                    searches[target_types] = [GenerationEntity(entity_id=item.entity_id,
                        entity_type=item.entity_type, display_name=item.display_name)
                        for item in response.candidates]
                intervention_scope.extend(searches[target_types])
            intervention_scope = _merge_entity_scope(intervention_scope)
        scenario_entity_ids = sorted({target for item in cycle.scenario.disruptions
            for target in _targets(item.get("payload", {}))})
        discovered_ids = sorted(item.entity_id for item in intervention_scope)
        planner_entity_ids = ((discovered_ids or scenario_entity_ids)
                              if known_entity_ids is None else known_entity_ids)
        request = PlannerRequest(planning_cycle_id=cycle.id, scenario_id=cycle.scenario.id,
            context_version=cycle.scenario.context_version, state_version=cycle.scenario.state_version,
            disruptions=cycle.scenario.disruptions, baseline_run_id=cycle.baseline_run_id,
            baseline_results=cycle.baseline_metrics, intervention_contracts=catalog.contracts,
            objectives=objectives or [], hard_constraints=hard_constraints or {},
            proposal_limit=proposal_limit,
            known_entity_ids=planner_entity_ids, entity_scope=intervention_scope,
            fixture_marker=fixture_marker)
        response = await self._planner_provider.propose_plans(request)
        contracts = {item.type: item for item in catalog.contracts}; known = set(request.known_entity_ids)
        plans = []
        for proposal in sorted(response.proposals, key=lambda item: item.proposal_id):
            normalized = []
            raw_keys = [_key({"type": item.type, "payload": item.payload}) for item in proposal.interventions]
            if len(raw_keys) != len(set(raw_keys)): raise ValueError("Duplicate interventions are not allowed")
            for intervention in proposal.interventions:
                contract = contracts.get(intervention.type)
                if contract is None: raise ValueError(f"Unknown intervention type: {intervention.type}")
                errors = validate_payload(intervention.payload, contract.payload_schema)
                if errors: raise ValueError(f"Invalid intervention payload: {errors}")
                if not _targets(intervention.payload).issubset(known):
                    raise ValueError("Intervention references an unknown entity ID")
                validated = await gateway.validate_intervention(InterventionValidationRequest(
                    intervention_type=intervention.type, payload=intervention.payload,
                    catalog_version=catalog.catalog_version, context_version=catalog.context_version,
                    schema_hash=contract.schema_hash))
                if not validated.valid or validated.normalized_payload is None:
                    raise ValueError(f"Client rejected intervention: {validated.errors}")
                normalized.append(validated.normalized_payload)
            plan_id = f"plan-{_key({'cycle': cycle.id, 'proposal': proposal.proposal_id, 'interventions': normalized})[:24]}"
            plans.append(PlanRecordView(id=plan_id, proposal_id=proposal.proposal_id, name=proposal.name,
                status=PlanningLifecycle.VALIDATED, interventions=normalized,
                planner_metadata=proposal.metadata.model_dump(mode="json"), rationale=proposal.rationale,
                assumptions=proposal.assumptions))
        return cycle.model_copy(update={"plans": plans,
            "planning_objectives": objectives or cycle.planning_objectives,
            "hard_constraints": hard_constraints or cycle.hard_constraints,
            "error_code": None, "error_message": None})

    async def submit_plan(self, cycle: PlanningCycle, plan_id: str, *, gateway: ClientGateway) -> PlanningCycle:
        plans = list(cycle.plans); index = next((i for i, item in enumerate(plans) if item.id == plan_id), None)
        if index is None: raise LookupError("Plan not found")
        plan = plans[index]
        accepted = await gateway.submit_simulation(SimulationSubmission(experiment_id=plan.id,
            idempotency_key=_key({"scenario": cycle.scenario.model_dump(mode="json"),
                                  "interventions": plan.interventions}),
            context_version=cycle.scenario.context_version, state_version=cycle.scenario.state_version,
            signal_version_ids=cycle.scenario.signal_version_ids, disruptions=cycle.scenario.disruptions,
            scenario_disruptions=cycle.scenario.disruptions,
            active_disruptions=cycle.scenario.active_disruptions,
            occurrence_probability=cycle.scenario.occurrence_probability,
            provenance={"planning_cycle_id": cycle.id, "baseline_run_id": cycle.baseline_run_id,
                        "interventions": plan.interventions}))
        plans[index] = plan.model_copy(update={"intervention_run_id": accepted.run_id,
            "status": PlanningLifecycle.RUNNING if accepted.status != "FAILED" else PlanningLifecycle.FAILED})
        updated = cycle.model_copy(update={"plans": plans})
        return await self.refresh_plan(updated, plan_id, gateway=gateway) if accepted.status == "COMPLETED" else updated

    async def refresh_plan(self, cycle: PlanningCycle, plan_id: str, *, gateway: ClientGateway) -> PlanningCycle:
        plans = list(cycle.plans); index = next((i for i, item in enumerate(plans) if item.id == plan_id), None)
        if index is None: raise LookupError("Plan not found")
        plan = plans[index]
        if plan.intervention_metrics is not None: return cycle
        if not plan.intervention_run_id: raise ValueError("Plan has not been submitted")
        status = await gateway.get_simulation(plan.intervention_run_id)
        if status.status == "FAILED": plans[index] = plan.model_copy(update={"status": PlanningLifecycle.FAILED})
        elif status.status == "COMPLETED":
            result = await gateway.get_simulation_results(plan.intervention_run_id,
                context_version=cycle.scenario.context_version, state_version=cycle.scenario.state_version,
                completed_at=status.updated_at)
            plans[index] = plan.model_copy(update={"status": PlanningLifecycle.EVALUATED,
                                                   "intervention_metrics": result.result})
        return cycle.model_copy(update={"plans": plans})

    def rank(self, cycle: PlanningCycle, *, metrics: tuple[str, ...] =
             ("late_shipments", "average_delay_hours", "total_cost"),
             hard_constraints: dict[str, float] | None = None) -> PlanningCycle:
        constraints = cycle.hard_constraints if hard_constraints is None else hard_constraints
        evaluated = []
        for plan in cycle.plans:
            if plan.status != PlanningLifecycle.EVALUATED or plan.intervention_metrics is None: continue
            reasons = [f"{name} exceeds {limit}" for name, limit in constraints.items()
                       if plan.intervention_metrics.get(name, float("inf")) > limit]
            values = tuple(plan.intervention_metrics.get(name, float("inf")) for name in metrics)
            evaluated.append((bool(reasons), values, plan.proposal_id, plan.id, reasons))
        evaluated.sort()
        rank_by_id = {item[3]: (rank, item[4]) for rank, item in enumerate(evaluated, 1)}
        plans = []
        for plan in cycle.plans:
            if plan.id not in rank_by_id: plans.append(plan); continue
            rank, reasons = rank_by_id[plan.id]
            plans.append(plan.model_copy(update={"rank": rank, "disqualification_reasons": reasons,
                "status": PlanningLifecycle.RECOMMENDED if rank == 1 and not reasons else PlanningLifecycle.EVALUATED,
                "ranking_explanation": f"Rank {rank} under lexicographic-v1 using {', '.join(metrics)}."}))
        return cycle.model_copy(update={"plans": plans,
            "status": PlanningLifecycle.RECOMMENDED if any(p.status == PlanningLifecycle.RECOMMENDED for p in plans)
                      else PlanningLifecycle.EVALUATED})

    def decide(self, cycle: PlanningCycle, plan_id: str, decision: PlanningLifecycle) -> PlanningCycle:
        if decision not in {PlanningLifecycle.APPROVED, PlanningLifecycle.REJECTED}:
            raise ValueError("Decision must be APPROVED or REJECTED")
        plans = list(cycle.plans); index = next((i for i, item in enumerate(plans) if item.id == plan_id), None)
        if index is None: raise LookupError("Plan not found")
        if decision == PlanningLifecycle.APPROVED and plans[index].status not in {
                PlanningLifecycle.RECOMMENDED, PlanningLifecycle.APPROVED}:
            raise ValueError("Only a recommendation can be approved")
        if decision == PlanningLifecycle.REJECTED and plans[index].status in {
                PlanningLifecycle.RUNNING, PlanningLifecycle.FAILED}:
            raise ValueError("A running or failed proposal cannot receive a decision")
        was_recommendation = plans[index].status == PlanningLifecycle.RECOMMENDED
        plans[index] = plans[index].model_copy(update={"status": decision})
        cycle_status = decision if decision == PlanningLifecycle.APPROVED or was_recommendation else cycle.status
        return cycle.model_copy(update={"plans": plans, "status": cycle_status})
