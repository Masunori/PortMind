"""Evidence workflows backed by a storage-neutral repository."""
from app.integrations.contracts import (DeletionImpact, DuplicateDeletionPreview,
    DuplicateDeletionResult, Evidence, EvidenceCreate, EvidenceKind, EvidenceUpdate)
from app.repositories import get_evidence_repository
from app.repositories.contracts import EvidenceRepository
from app.repositories.errors import ConflictError, NotFoundError, ValidationError

def _repo(repository: EvidenceRepository | None = None) -> EvidenceRepository: return repository or get_evidence_repository()
def store_evidence(values: EvidenceCreate, repository: EvidenceRepository | None = None) -> tuple[Evidence, bool]:
    try: return _repo(repository).store(values)
    except NotFoundError as error: raise LookupError(str(error)) from error
def list_evidence(*, archived: bool | None = False, kind: EvidenceKind | None = None,
                  include_duplicates: bool = False, limit: int = 50, offset: int = 0,
                  repository: EvidenceRepository | None = None) -> list[Evidence]:
    repository = _repo(repository)
    token = None
    skipped = 0
    while True:
        page = repository.list(archived=archived, kind=kind,
            include_duplicates=include_duplicates, limit=min(1000, offset + limit),
            continuation_token=token)
        if skipped + len(page.items) > offset or page.continuation_token is None:
            start = max(0, offset - skipped)
            return list(page.items[start:start + limit])
        skipped += len(page.items)
        token = page.continuation_token
def get_evidence(evidence_id: str, repository: EvidenceRepository | None = None) -> Evidence | None: return _repo(repository).get(evidence_id)
def evidence_has_signal(evidence_id: str, repository: EvidenceRepository | None = None) -> bool: return _repo(repository).has_signal(evidence_id)
def _legacy_errors(operation):
    try: return operation()
    except NotFoundError as error: raise LookupError(str(error)) from error
    except ValidationError as error: raise ValueError(str(error)) from error
    except ConflictError as error: raise PermissionError(str(error)) from error
def set_archived(evidence_id: str, archived: bool, repository: EvidenceRepository | None = None) -> Evidence: return _legacy_errors(lambda: _repo(repository).set_archived(evidence_id, archived))
def deletion_impact(evidence_id: str, repository: EvidenceRepository | None = None) -> DeletionImpact: return _legacy_errors(lambda: _repo(repository).deletion_impact(evidence_id))
def duplicate_deletion_preview(evidence_id: str, repository: EvidenceRepository | None = None) -> DuplicateDeletionPreview: return _legacy_errors(lambda: _repo(repository).duplicate_deletion_preview(evidence_id))
def delete_unprotected_duplicates(evidence_id: str, *, delete_canonical: bool = False,
                                  repository: EvidenceRepository | None = None) -> DuplicateDeletionResult: return _legacy_errors(lambda: _repo(repository).delete_unprotected_duplicates(evidence_id, delete_canonical=delete_canonical))
def remove_raw_content(evidence_id: str, repository: EvidenceRepository | None = None) -> Evidence: return _legacy_errors(lambda: _repo(repository).remove_raw_content(evidence_id))
def update_evidence(evidence_id: str, values: EvidenceUpdate, repository: EvidenceRepository | None = None) -> Evidence: return _legacy_errors(lambda: _repo(repository).update(evidence_id, values))
def delete_evidence(evidence_id: str, repository: EvidenceRepository | None = None) -> None: _legacy_errors(lambda: _repo(repository).delete(evidence_id))
