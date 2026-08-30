"""End-to-end provider, grounding, mapping, validation, and review tests."""

import asyncio

import pytest

from app.domain.source import DataSourceCreate, SourceType
from app.integrations.contracts import DisruptionCatalog, DisruptionContract, EntityCandidate, EvidenceCreate, EvidenceKind
from app.integrations.schema_validation import schema_hash
from app.integrations.providers import (
    ProviderBundle, StubEffectMappingProvider, StubFilterProvider,
    StubInterpreterProvider, StubRelationshipProvider,
)
from app.services.evidence_service import store_evidence
from app.services.signal_service import (
    get_evidence_processing_eligibility, list_signals, process_evidence,
    review_signal,
)
from app.services import signal_service
from app.services.source_service import create_source
from tests.fakes import FakeClientGateway


def run(value): return asyncio.run(value)


def providers() -> ProviderBundle:
    return ProviderBundle(filter=StubFilterProvider(), interpreter=StubInterpreterProvider(),
        effect_mapping=StubEffectMappingProvider(), relationship=StubRelationshipProvider())


def gateway() -> FakeClientGateway:
    return FakeClientGateway(entities=[EntityCandidate(
        entity_id="hph", display_name="Hai Phong", entity_type="port", confidence=1)])


def test_accepted_evidence_becomes_grounded_client_normalized_reviewable_signal(test_session_factory):
    source = create_source(DataSourceCreate(name="Reports", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.UPLOAD,
        title="Port alert", media_type="text/plain", content="Hai Phong port may close tomorrow"))
    client = gateway()
    signal = run(process_evidence(evidence.id, gateway=client, providers=providers()))
    assert signal.classification == "FORECAST"
    assert signal.entities[0].entity_id == "hph"
    assert signal.processing_state == "READY_FOR_REVIEW"
    assert signal.mapping_outcome == "MAPPED"
    assert signal.normalized_disruption["payload"]["target_ids"] == ["hph"]
    assert signal.normalized_disruption["payload"]["effective_from"] == signal.temporal_window.starts_at.isoformat()
    assert any(name == "get_entity_resolution_capabilities" for name, _ in client.calls)
    assert [item.id for item in list_signals(review_status="PENDING")] == [signal.id]
    assert list_signals(review_status="PENDING", limit=1, offset=1) == []
    accepted = review_signal(signal.signal_id, "ACCEPTED")
    assert accepted.lifecycle_status == "ACTIVE"
    assert accepted.review_status == "ACCEPTED"
    assert list_signals(review_status="PENDING") == []


def test_rejected_evidence_does_not_create_a_signal(test_session_factory):
    source = create_source(DataSourceCreate(name="Reports", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.UPLOAD,
        title="Cafeteria menu", media_type="text/plain", content="Lunch today is noodles"))
    assert run(process_evidence(evidence.id, gateway=gateway(), providers=providers())) is None


def test_unresolved_signal_cannot_be_accepted(test_session_factory):
    source = create_source(DataSourceCreate(name="Reports", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.UPLOAD,
        title="Port alert", media_type="text/plain", content="PSA Singapore port may close"))
    signal = run(process_evidence(evidence.id, gateway=gateway(), providers=providers()))
    assert signal.entities[0].status == "NOT_FOUND"
    assert signal.processing_state == "NEEDS_RESOLUTION"
    assert signal.mapping_outcome == "UNRESOLVED_ENTITIES"
    assert signal.mapping_errors
    with pytest.raises(ValueError, match="resolved"):
        review_signal(signal.signal_id, "ACCEPTED")


def test_rejected_signal_allows_lineage_linked_reprocessing(test_session_factory):
    source = create_source(DataSourceCreate(name="Retry reports", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.UPLOAD, title="Retry port alert",
        media_type="text/plain", content="Singapore port may close during storm",
    ))
    first = run(process_evidence(evidence.id, gateway=gateway(), providers=providers()))
    assert first.processing_state == "NEEDS_RESOLUTION"
    review_signal(first.signal_id, "REJECTED")

    eligibility = get_evidence_processing_eligibility(evidence.id)
    assert eligibility.can_process is True
    assert eligibility.retry_of_signal_id == first.signal_id
    assert eligibility.attempts[0].review_status == "REJECTED"

    retried = run(process_evidence(evidence.id, gateway=gateway(), providers=providers()))
    assert retried.signal_id != first.signal_id
    assert retried.retry_of_signal_id == first.signal_id
    assert retried.review_status == "PENDING"
    assert get_evidence_processing_eligibility(evidence.id).can_process is False
    assert list_signals(review_status="REJECTED")[0].signal_id == first.signal_id


def test_pending_signal_blocks_duplicate_processing_attempt(test_session_factory):
    source = create_source(DataSourceCreate(name="Pending reports", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.UPLOAD, title="Pending port alert",
        media_type="text/plain", content="Hai Phong port may close next week",
    ))
    first = run(process_evidence(evidence.id, gateway=gateway(), providers=providers()))
    eligibility = get_evidence_processing_eligibility(evidence.id)
    assert eligibility.can_process is False
    assert eligibility.blocked_by == ["signal_pending"]
    with pytest.raises(ValueError, match="pending or accepted"):
        run(process_evidence(evidence.id, gateway=gateway(), providers=providers()))
    assert list_signals(review_status="PENDING")[0].signal_id == first.signal_id


def test_related_entities_are_retained_but_only_targets_are_mapped(test_session_factory):
    source = create_source(DataSourceCreate(name="Network report", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.UPLOAD, title="Network disruption",
        media_type="text/plain", content=(
            "Hai Phong may close, delaying Supplier VN cargo through PSA Singapore "
            "and Singapore Warehouse to Customer SG."
        ),
    ))

    signal = run(process_evidence(evidence.id, gateway=gateway(), providers=providers()))

    assert signal.processing_state == "READY_FOR_REVIEW"
    assert [entity.mention for entity in signal.entities] == [
        "Hai Phong", "Supplier VN", "PSA Singapore",
        "Singapore Warehouse", "Customer SG",
    ]
    assert [entity.mention for entity in signal.entities if entity.is_target] == ["Hai Phong"]
    assert all(entity.status == "NOT_FOUND" for entity in signal.entities if not entity.is_target)
    assert signal.normalized_disruption["payload"]["target_ids"] == ["hph"]


def test_unexpected_mapping_exception_becomes_terminal_failure(
    test_session_factory, monkeypatch: pytest.MonkeyPatch,
):
    source = create_source(DataSourceCreate(name="Failure report", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(
        source_id=source.id, kind=EvidenceKind.UPLOAD, title="Mapping exception",
        media_type="text/plain", content="Hai Phong port may close",
    ))
    monkeypatch.setattr(
        signal_service, "validate_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TypeError("validator defect")),
    )

    signal = run(process_evidence(evidence.id, gateway=gateway(), providers=providers()))

    assert signal.processing_state == "MAPPING_FAILED"
    assert signal.mapping_outcome == "PROCESSING_FAILED"
    assert signal.mapping_errors == [
        "Mapping failed unexpectedly; reject and reprocess this signal"]


def test_incompatible_entity_type_is_a_persisted_local_mapping_failure(test_session_factory):
    source = create_source(DataSourceCreate(name="Reports", type=SourceType.UPLOAD))
    evidence, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.UPLOAD,
        title="Port alert", media_type="text/plain", content="Hai Phong port may close"))
    client = gateway()
    base_contract = run(client.get_disruption_contracts()).contracts[0]
    incompatible = DisruptionContract(type=base_contract.type, target_types=["EDGE"],
        payload_schema=base_contract.payload_schema, schema_hash=schema_hash(base_contract.payload_schema))
    client.responses["catalog"] = DisruptionCatalog(catalog_version="catalog-v2",
        context_version=client.context.context_version, capability_version=client.context.capability_version,
        contracts=[incompatible])

    signal = run(process_evidence(evidence.id, gateway=client, providers=providers()))

    assert signal.processing_state == "MAPPING_FAILED"
    assert signal.mapping_outcome == "LOCAL_VALIDATION_FAILED"
    assert "entity type" in signal.mapping_errors[0]
    assert not any(name == "validate_disruption" for name, _ in client.calls)
