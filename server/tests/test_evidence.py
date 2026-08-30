"""Unified evidence lifecycle tests."""

from datetime import datetime, timezone
import pytest

from app.domain.source import DataSourceCreate, SourceType
from app.integrations.contracts import EvidenceCreate, EvidenceKind, EvidenceUpdate
from app.models import EvidenceRecord
from app.services.evidence_service import delete_evidence, delete_unprotected_duplicates, deletion_impact, duplicate_deletion_preview, list_evidence, remove_raw_content, set_archived, store_evidence, update_evidence
from app.services.source_service import create_source


def test_structured_and_unstructured_evidence_share_envelope_and_link_duplicates(test_session_factory):
    source = create_source(DataSourceCreate(name="API", type=SourceType.UPLOAD))
    first, duplicate = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.STRUCTURED,
        title="Record", media_type="application/json", structured_content={"port": "HPH", "delay": 12}))
    second, is_duplicate = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.API,
        title="Same record", media_type="application/json", structured_content={"delay": 12, "port": "HPH"}))
    assert duplicate is False
    assert is_duplicate is True
    assert second.duplicate_of_id == first.id
    assert second.structured_content is None
    assert [item.id for item in list_evidence()] == [first.id]
    assert len(list_evidence(include_duplicates=True)) == 2


def test_archive_restore_and_raw_removal_preserve_audit_metadata(test_session_factory):
    source = create_source(DataSourceCreate(name="Manual", type=SourceType.UPLOAD))
    item, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.MANUAL,
        title="Observation", media_type="text/plain", content=" Port   closure "))
    assert set_archived(item.id, True).archived_at is not None
    assert list_evidence() == []
    assert set_archived(item.id, False).archived_at is None
    impact = deletion_impact(item.id)
    assert impact.can_delete_permanently is True
    redacted = remove_raw_content(item.id)
    assert redacted.content is None
    assert redacted.content_reference == "removed://retained-audit-metadata"
    assert redacted.content_hash == item.content_hash


def test_unprotected_evidence_can_be_edited_and_deleted(test_session_factory):
    source = create_source(DataSourceCreate(name="Manual edit", type=SourceType.UPLOAD))
    item, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.MANUAL,
        title="Draft", media_type="text/plain", content="Initial content"))
    updated = update_evidence(item.id, EvidenceUpdate(title="Corrected", content="Correct content"))
    assert updated.title == "Corrected"
    assert updated.content_hash != item.content_hash
    delete_evidence(item.id)
    assert list_evidence() == []


def test_duplicate_provenance_blocks_original_until_duplicate_is_deleted(test_session_factory):
    source = create_source(DataSourceCreate(name="Duplicate cleanup", type=SourceType.UPLOAD))
    original, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.MANUAL,
        title="Original", media_type="text/plain", content="Same retained content"))
    duplicate, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.MANUAL,
        title="Duplicate", media_type="text/plain", content="Same retained content"))
    impact = deletion_impact(original.id)
    assert impact.can_delete_permanently is False
    assert impact.protected_by == ["duplicate_evidence"]
    with pytest.raises(PermissionError, match="audit workflow"):
        delete_evidence(original.id)
    delete_evidence(duplicate.id)
    assert deletion_impact(original.id).can_delete_permanently is True
    delete_evidence(original.id)


def test_batch_duplicate_cleanup_deletes_eligible_and_reports_protected(test_session_factory):
    source = create_source(DataSourceCreate(name="Batch duplicate cleanup", type=SourceType.UPLOAD))
    original, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.MANUAL,
        title="Original", media_type="text/plain", content="Repeated collection body"))
    eligible, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.API,
        title="Eligible duplicate", media_type="text/plain", content="Repeated collection body"))
    protected, _ = store_evidence(EvidenceCreate(source_id=source.id, kind=EvidenceKind.WEBSITE,
        title="Protected duplicate", media_type="text/plain", content="Repeated collection body"))
    with test_session_factory.begin() as session:
        session.get(EvidenceRecord, protected.id).legal_hold = True
    preview = duplicate_deletion_preview(original.id)
    assert [item.evidence_id for item in preview.candidates] == [eligible.id, protected.id]
    result = delete_unprotected_duplicates(original.id, delete_canonical=True)
    assert result.deleted_ids == [eligible.id]
    assert result.skipped[0].evidence_id == protected.id
    assert result.skipped[0].protected_by == ["legal_hold"]
    assert result.canonical_deleted is False
    assert deletion_impact(original.id).protected_by == ["duplicate_evidence"]
