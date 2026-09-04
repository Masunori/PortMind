"""Storage-neutral behaviors run through backend-provided repository fixtures."""

import pytest
from datetime import datetime, timedelta, timezone

from app.domain.source import DataSourceCreate, SourceType
from app.domain.plan import FrozenScenario, Plan, PlanAction, PlanStatus, PlanningCycle, PlanningLifecycle
from app.domain.scenario import Scenario
from app.integrations.contracts import (EvidenceCreate, EvidenceKind, EvidenceUpdate,
    ExperimentPackage, GroundedEntity, InterpretationProposal, ProviderMetadata,
    SignalClass, TemporalWindow)
from app.domain.repository import SimulationResultSnapshot
from app.repositories.contracts import (EvidenceRepository, ExperimentRepository, PlanRepository,
    PlanningCycleRepository, PromptRepository, ScenarioRepository, SignalRepository, SourceRepository)
from app.repositories.errors import ConflictError, NotFoundError, ValidationError


def source(name: str) -> DataSourceCreate:
    return DataSourceCreate(name=name, type=SourceType.WEBSITE, url="https://example.com",
                            scrape_interval_minutes=30, scraper_type="HTML")


def test_adapters_implement_runtime_contracts(repository_factories) -> None:
    contracts={"source":SourceRepository,"evidence":EvidenceRepository,
        "prompt":PromptRepository,"scenario":ScenarioRepository,"plan":PlanRepository,
        "signal":SignalRepository,"experiment":ExperimentRepository,
        "planning":PlanningCycleRepository}
    for name,contract in contracts.items():
        assert isinstance(repository_factories[name](),contract)


def test_source_pagination_is_stable_and_tokens_are_validated(repository_factories) -> None:
    repository = repository_factories["source"]()
    for name in ("Charlie", "alpha", "Bravo"):
        repository.create(source(name))
    first = repository.list(limit=2)
    second = repository.list(limit=2, continuation_token=first.continuation_token)
    assert [item.name for item in first.items] == ["alpha", "Bravo"]
    assert [item.name for item in second.items] == ["Charlie"]
    assert second.continuation_token is None
    with pytest.raises(ValidationError, match="continuation token"):
        repository.list(continuation_token="invalid")

def test_source_collection_lease_is_exclusive_and_owner_scoped(repository_factories) -> None:
    repository=repository_factories["source"]();item=repository.create(source("Leased"))
    now=datetime.now(timezone.utc);expires=now+timedelta(minutes=5)
    assert repository.acquire_lease(item.id,"worker-one",now=now,expires_at=expires)
    assert not repository.acquire_lease(item.id,"worker-two",now=now,expires_at=expires)
    repository.release_lease(item.id,"worker-two")
    assert not repository.acquire_lease(item.id,"worker-two",now=now,expires_at=expires)
    repository.release_lease(item.id,"worker-one")
    assert repository.acquire_lease(item.id,"worker-two",now=now,expires_at=expires)


def test_planning_snapshot_rejects_a_stale_expected_version(repository_factories) -> None:
    repository = repository_factories["planning"]()
    scenario = FrozenScenario(id="scenario-one", proposal_id="proposal-one", name="One",
        context_version="context-v1", state_version="state-v1",
        disruptions=[{"type":"DELAY","payload":{}}], occurrence_probability=0.5,
        provenance={})
    stale = PlanningCycle(id="cycle-one", scenario=scenario, status=PlanningLifecycle.PROPOSED)
    current = repository.save(stale.model_copy(deep=True), expected_version=0)
    assert current.version == 1
    with pytest.raises(ConflictError, match="version conflict"):
        repository.save(stale.model_copy(deep=True), expected_version=0)
    assert repository.get(current.id) == current


def test_failed_transaction_rolls_back_result_copy(repository_factories) -> None:
    repository=repository_factories["experiment"]()
    snapshot=SimulationResultSnapshot(run_id="orphan-run",context_version="context-v1",
        state_version="state-v1",result={"value":1},completed_at=datetime.now(timezone.utc))
    with pytest.raises(NotFoundError,match="Experiment not found"):
        repository.save_result("missing-experiment",snapshot)
    assert repository.get_result(snapshot.run_id) is None


def test_definition_repositories_round_trip_and_enforce_transitions(repository_factories) -> None:
    prompts=repository_factories["prompt"]();scenarios=repository_factories["scenario"]();plans=repository_factories["plan"]()
    assert prompts.save("filter","custom").prompt=="custom"
    assert prompts.get("filter").is_custom is True
    assert prompts.reset("filter") is True and prompts.get("filter") is None
    scenario=Scenario(id="scenario-contract",name="Contract",probability=0.25,disruptions=[{"type":"DELAY","payload":{"hours":1.5}}])
    assert scenarios.save(scenario)==scenario and scenarios.get(scenario.id)==scenario
    plan=Plan(id="plan-contract",name="Contract",actions=[PlanAction(type="REROUTE",target_ids=["one"],payload={})])
    plans.save(plan)
    with pytest.raises(ValueError,match="recommended"):
        plans.set_status(plan.id,PlanStatus.APPROVED)
    recommended=plans.save(plan.model_copy(update={"status":PlanStatus.RECOMMENDED}))
    assert plans.set_status(recommended.id,PlanStatus.APPROVED).status is PlanStatus.APPROVED


def test_evidence_round_trip_deduplication_and_source_protection(repository_factories) -> None:
    sources=repository_factories["source"]();evidence=repository_factories["evidence"]()
    owner=sources.create(DataSourceCreate(name="Evidence owner",type=SourceType.UPLOAD))
    values=EvidenceCreate(source_id=owner.id,kind=EvidenceKind.UPLOAD,title="One",media_type="text/plain",content="multibyte é content")
    canonical,duplicate=evidence.store(values);copy,is_duplicate=evidence.store(values.model_copy(update={"title":"Two"}))
    assert duplicate is False and is_duplicate is True and copy.duplicate_of_id==canonical.id
    assert evidence.get(canonical.id).content=="multibyte é content"
    with pytest.raises(ConflictError,match="retained evidence"):
        sources.delete(owner.id)
    evidence.delete(copy.id)
    updated=evidence.update(canonical.id,EvidenceUpdate(title="Updated"))
    assert updated.title=="Updated"


def test_signal_experiment_and_result_lifecycle(repository_factories) -> None:
    sources=repository_factories["source"]();evidence_repo=repository_factories["evidence"]();signals=repository_factories["signal"]();experiments=repository_factories["experiment"]()
    owner=sources.create(DataSourceCreate(name="Signal owner",type=SourceType.UPLOAD))
    evidence,_=evidence_repo.store(EvidenceCreate(source_id=owner.id,kind=EvidenceKind.UPLOAD,title="Signal",media_type="text/plain",content="Port delay"))
    proposal=InterpretationProposal(classification=SignalClass.FORECAST,signal_type="DELAY",entity_mentions=["Port"],target_entity_mentions=["Port"],temporal_window=TemporalWindow(),occurrence_probability=.5,severity=.4,extraction_confidence=.9,supporting_evidence_ids=[evidence.id],metadata=ProviderMetadata(provider="stub",model="stub",prompt_version="v1",stub=True))
    version_id=signals.create_candidate(evidence,proposal,"context-v1",None)
    signals.add_entity(version_id,GroundedEntity(mention="Port",is_target=True,status="RESOLVED",entity_id="port-1",entity_type="PORT",method="exact",confidence=1,context_version="context-v1"))
    signals.add_effect(version_id,outcome="MAPPED",errors=[],mapping_proposal={},local_validation={"valid":True},client_validation={"valid":True},normalized_disruption={"type":"DELAY","payload":{}},catalog_version="catalog-v1",schema_hash="hash",context_version="context-v1")
    ready=signals.finalize(version_id,1,.8);accepted=signals.review(ready.signal_id,"ACCEPTED",expected_version=ready.aggregate_version)
    assert accepted.review_status=="ACCEPTED" and evidence_repo.has_signal(evidence.id)
    package=ExperimentPackage(id="experiment-contract",name="Contract",context_version="context-v1",state_version="state-v1",signal_version_ids=[version_id],disruptions=[accepted.normalized_disruption],occurrence_probability=.5,provenance={},validation_summary={},idempotency_key="contract-key",created_at=datetime.now(timezone.utc),status="READY")
    assert experiments.create_if_absent(package).id==experiments.create_if_absent(package.model_copy(update={"id":"other-id"})).id
    snapshot=SimulationResultSnapshot(run_id="contract-run",context_version="context-v1",state_version="state-v1",result={"ok":True},completed_at=datetime.now(timezone.utc))
    experiments.save_result(package.id,snapshot)
    stored=experiments.get_result(snapshot.run_id)
    assert stored.run_id==snapshot.run_id and stored.result==snapshot.result
