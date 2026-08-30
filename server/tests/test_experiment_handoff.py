"""Immutable scenario package and simulation handoff tests."""

import asyncio

import pytest
from sqlalchemy import select

from app.domain.source import DataSourceCreate, SourceType
from app.integrations.contracts import EntityCandidate, EvidenceCreate, EvidenceKind
from app.integrations.providers import ProviderBundle, StubEffectMappingProvider, StubFilterProvider, StubInterpreterProvider, StubRelationshipProvider
from app.models import SignalRelationshipRecord, SimulationResultCopyRecord
from app.services.evidence_service import store_evidence
from app.services.experiment_service import create_experiment, refresh_results, submit_experiment
from app.services.signal_service import process_evidence, review_signal
from app.services.source_service import create_source
from tests.fakes import FakeClientGateway


def run(value): return asyncio.run(value)


def test_experiment_is_reproducible_idempotent_and_stores_result_copy(test_session_factory):
    gateway = FakeClientGateway(entities=[EntityCandidate(
        entity_id="hph", display_name="Hai Phong", entity_type="port", confidence=1)])
    bundle = ProviderBundle(filter=StubFilterProvider(), interpreter=StubInterpreterProvider(),
        effect_mapping=StubEffectMappingProvider(), relationship=StubRelationshipProvider())
    source = create_source(DataSourceCreate(name="Reports", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.UPLOAD,
        title="Port closure", media_type="text/plain", content="Hai Phong port may close"))
    signal = run(process_evidence(evidence.id, gateway=gateway, providers=bundle))
    review_signal(signal.signal_id, "ACCEPTED")
    first = run(create_experiment("Closure case", [signal.id], gateway=gateway))
    second = run(create_experiment("Closure case", [signal.id], gateway=gateway))
    assert first.id == second.id
    submitted = run(submit_experiment(first.id, gateway=gateway))
    result = run(refresh_results(first.id, gateway=gateway))
    assert submitted.client_run_id == result["run_id"]
    with test_session_factory() as session:
        assert session.scalar(select(SimulationResultCopyRecord)).run_id == result["run_id"]


def test_mutually_exclusive_signals_are_rejected(test_session_factory):
    # Relationship enforcement is deterministic and happens before client submission.
    from app.services.experiment_service import _validate_relationships
    relationship = SignalRelationshipRecord(id="rel", source_signal_version_id="a",
        target_signal_version_id="b", relationship="MUTUALLY_EXCLUSIVE", confidence=1,
        rationale="fixtures", created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    with pytest.raises(ValueError, match="Mutually exclusive"):
        _validate_relationships(["a", "b"], [relationship])
