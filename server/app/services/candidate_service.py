"""Extract, ground, validate, version, and confirm disruption candidates."""

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select

from app.ai.base import AIProvider
from app.ai.schemas import DisruptionExtraction
from app.database import SessionLocal
from app.domain.assessment import RelevanceDecision
from app.domain.candidate import (
    CandidateProvenance,
    CandidateReviewStatus,
    CandidateUpdate,
    CandidateValidationStatus,
    CandidateVersion,
    DisruptionCandidate,
)
from app.domain.disruption import Disruption, DisruptionEffects, DisruptionType
from app.domain.exposure import ExposureAnalysis
from app.models import (
    CandidateVersionRecord,
    DisruptionCandidateRecord,
    DocumentAssessmentRecord,
    RawDocumentRecord,
)
from app.services.alias_service import resolve_node_ids
from app.services.disruption_service import save_disruption
from app.services.event_service import group_event
from app.services.exposure_service import analyze_exposure
from app.services.network_service import get_network
from app.services.ai_context import build_interpreter_context


def _to_domain(record: DisruptionCandidateRecord) -> DisruptionCandidate:
    """Convert one candidate record into its public contract."""

    return DisruptionCandidate(
        id=record.id,
        document_id=record.document_id,
        event_id=record.event_id,
        disruption_type=record.disruption_type,
        affected_locations=record.affected_locations,
        affected_node_ids=record.affected_node_ids,
        affected_edge_ids=record.affected_edge_ids,
        start_time=record.start_time,
        end_time=record.end_time,
        probability=record.probability,
        severity=record.severity,
        effects=record.effects_json,
        summary=record.summary,
        extraction_confidence=record.extraction_confidence,
        validation_status=CandidateValidationStatus(record.validation_status),
        validation_errors=record.validation_errors,
        review_status=CandidateReviewStatus(record.review_status),
        confirmed_disruption_id=record.confirmed_disruption_id,
        run_id=record.run_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _validation_errors(record: DisruptionCandidateRecord) -> list[str]:
    """Return all deterministic validation failures without short-circuiting."""

    errors: list[str] = []
    try:
        DisruptionType(record.disruption_type)
    except ValueError:
        errors.append("Unsupported disruption type")
    if not 0 <= record.probability <= 1:
        errors.append("Probability must be between 0 and 1")
    if not 0 <= record.severity <= 1:
        errors.append("Severity must be between 0 and 1")
    if record.end_time <= record.start_time:
        errors.append("End time must be after start time")
    network = get_network()
    node_ids = {node.id for node in network.nodes}
    edge_ids = {edge.id for edge in network.edges}
    if not record.affected_node_ids and not record.affected_edge_ids:
        errors.append("At least one grounded target is required")
    if not set(record.affected_node_ids) <= node_ids:
        errors.append("Candidate contains an unknown node")
    if not set(record.affected_edge_ids) <= edge_ids:
        errors.append("Candidate contains an unknown edge")
    try:
        DisruptionEffects.model_validate(record.effects_json)
    except ValidationError as error:
        errors.append(f"Unsupported effects: {error.errors()[0]['msg']}")
    with SessionLocal() as session:
        if session.get(RawDocumentRecord, record.document_id) is None:
            errors.append("Source document does not exist")
    return errors


def _ground(locations: list[str]) -> tuple[list[str], list[str], list[str]]:
    """Resolve locations to nodes and their incident edges."""

    node_ids, unresolved = resolve_node_ids(locations)
    network = get_network()
    edge_ids = sorted(
        edge.id
        for edge in network.edges
        if edge.source_id in node_ids or edge.target_id in node_ids
    )
    return node_ids, edge_ids, unresolved


async def extract_candidate(document_id: str, provider: AIProvider) -> DisruptionCandidate:
    """Extract facts only from an effectively relevant document, then validate."""

    with SessionLocal() as session:
        document = session.get(RawDocumentRecord, document_id)
        assessment = session.get(DocumentAssessmentRecord, document_id)
        if document is None:
            raise LookupError("Document not found")
        if assessment is None:
            raise ValueError("Document must be assessed before extraction")
        effective = assessment.human_override or assessment.decision
        if effective != RelevanceDecision.RELEVANT.value:
            raise ValueError("Only relevant documents can produce candidates")
        title, content = document.title, document.content
    extraction = await provider.structured_generate(
        "Extract disruption facts using human-readable locations only. Never invent "
        f"internal IDs.\n{build_interpreter_context(content[:1000]).text}\nTitle: {title}\nDocument: {content[:12000]}",
        DisruptionExtraction,
    )
    node_ids, edge_ids, unresolved = _ground(extraction.affected_locations)
    now = datetime.now(timezone.utc)
    record = DisruptionCandidateRecord(
        id=f"candidate-{uuid4().hex}",
        document_id=document_id,
        event_id=None,
        disruption_type=extraction.disruption_type,
        affected_locations=extraction.affected_locations,
        affected_node_ids=node_ids,
        affected_edge_ids=edge_ids,
        start_time=extraction.start_time_hours,
        end_time=extraction.end_time_hours,
        probability=extraction.probability,
        severity=extraction.severity,
        effects_json=extraction.effects,
        summary=extraction.summary,
        extraction_confidence=extraction.confidence,
        validation_status=CandidateValidationStatus.EXTRACTED.value,
        validation_errors=[f"Unresolved location: {item}" for item in unresolved],
        review_status=CandidateReviewStatus.PENDING.value,
        confirmed_disruption_id=None,
        run_id=None,
        created_at=now,
        updated_at=now,
    )
    errors = record.validation_errors + _validation_errors(record)
    record.validation_errors = errors
    record.validation_status = (
        CandidateValidationStatus.INVALID.value
        if errors
        else CandidateValidationStatus.VALIDATED.value
    )
    if not errors:
        record.event_id = group_event(
            document_id,
            record.disruption_type,
            record.affected_node_ids + record.affected_edge_ids,
            record.start_time,
            record.end_time,
        )
    with SessionLocal.begin() as session:
        session.add(record)
    return _to_domain(record)


def get_candidates() -> list[DisruptionCandidate]:
    """Return candidates newest first."""

    with SessionLocal() as session:
        records = session.scalars(
            select(DisruptionCandidateRecord).order_by(
                DisruptionCandidateRecord.created_at.desc(),
                DisruptionCandidateRecord.id,
            )
        ).all()
    return [_to_domain(record) for record in records]


def get_candidate(candidate_id: str) -> DisruptionCandidate | None:
    """Return one candidate or ``None``."""

    with SessionLocal() as session:
        record = session.get(DisruptionCandidateRecord, candidate_id)
        return _to_domain(record) if record is not None else None


def _snapshot(record: DisruptionCandidateRecord) -> dict[str, object]:
    """Build a JSON-safe snapshot of mutable candidate fields."""

    return {
        "disruption_type": record.disruption_type,
        "affected_locations": record.affected_locations,
        "affected_node_ids": record.affected_node_ids,
        "affected_edge_ids": record.affected_edge_ids,
        "start_time": record.start_time,
        "end_time": record.end_time,
        "probability": record.probability,
        "severity": record.severity,
        "effects": record.effects_json,
        "summary": record.summary,
        "validation_status": record.validation_status,
        "validation_errors": record.validation_errors,
    }


def update_candidate(candidate_id: str, values: CandidateUpdate) -> DisruptionCandidate:
    """Version, apply, reground, and revalidate an operator edit."""

    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        record = session.get(DisruptionCandidateRecord, candidate_id)
        if record is None:
            raise LookupError("Candidate not found")
        if record.review_status != CandidateReviewStatus.PENDING.value:
            raise ValueError("Reviewed candidates cannot be edited")
        version = session.scalar(
            select(func.count(CandidateVersionRecord.id)).where(
                CandidateVersionRecord.candidate_id == candidate_id
            )
        ) or 0
        session.add(
            CandidateVersionRecord(
                candidate_id=candidate_id,
                version=version + 1,
                snapshot=_snapshot(record),
                reason="OPERATOR_EDIT",
                created_at=now,
            )
        )
        changes = values.model_dump(exclude_unset=True)
        locations = changes.pop("affected_locations", None)
        effects = changes.pop("effects", None)
        for field, value in changes.items():
            setattr(record, field, value)
        if effects is not None:
            record.effects_json = effects
        if locations is not None:
            record.affected_locations = locations
            nodes, edges, unresolved = _ground(locations)
            record.affected_node_ids = nodes
            record.affected_edge_ids = edges
        else:
            unresolved = []
        errors = [f"Unresolved location: {item}" for item in unresolved]
        errors.extend(_validation_errors(record))
        record.validation_errors = errors
        record.validation_status = (
            CandidateValidationStatus.INVALID.value
            if errors
            else CandidateValidationStatus.VALIDATED.value
        )
        record.updated_at = now
    return _to_domain(record)


def reject_candidate(candidate_id: str) -> DisruptionCandidate:
    """Mark a pending candidate rejected without deleting evidence."""

    with SessionLocal.begin() as session:
        record = session.get(DisruptionCandidateRecord, candidate_id)
        if record is None:
            raise LookupError("Candidate not found")
        if record.review_status != CandidateReviewStatus.PENDING.value:
            raise ValueError("Candidate has already been reviewed")
        record.review_status = CandidateReviewStatus.REJECTED.value
        record.updated_at = datetime.now(timezone.utc)
    return _to_domain(record)


def confirm_candidate(candidate_id: str) -> DisruptionCandidate:
    """Create a real disruption only from a valid, pending candidate."""

    candidate = get_candidate(candidate_id)
    if candidate is None:
        raise LookupError("Candidate not found")
    if candidate.validation_status is not CandidateValidationStatus.VALIDATED:
        raise ValueError("Only validated candidates can be confirmed")
    if candidate.review_status is not CandidateReviewStatus.PENDING:
        raise ValueError("Candidate has already been reviewed")
    disruption_id = f"confirmed-{candidate.id}"
    save_disruption(
        Disruption(
            id=disruption_id,
            type=DisruptionType(candidate.disruption_type),
            affected_node_ids=candidate.affected_node_ids,
            affected_edge_ids=candidate.affected_edge_ids,
            start_time=candidate.start_time,
            end_time=candidate.end_time,
            effects=DisruptionEffects.model_validate(candidate.effects),
        )
    )
    with SessionLocal.begin() as session:
        record = session.get(DisruptionCandidateRecord, candidate_id)
        record.review_status = CandidateReviewStatus.ACCEPTED.value
        record.confirmed_disruption_id = disruption_id
        record.updated_at = datetime.now(timezone.utc)
    return _to_domain(record)


def get_candidate_versions(candidate_id: str) -> list[CandidateVersion]:
    """Return immutable edit history in version order."""

    with SessionLocal() as session:
        records = session.scalars(
            select(CandidateVersionRecord)
            .where(CandidateVersionRecord.candidate_id == candidate_id)
            .order_by(CandidateVersionRecord.version)
        ).all()
    return [
        CandidateVersion(
            version=item.version,
            snapshot=item.snapshot,
            reason=item.reason,
            created_at=item.created_at,
        )
        for item in records
    ]


def attach_candidate_run(candidate_id: str, run_id: str) -> DisruptionCandidate:
    """Attach an observable decision-pipeline run to a confirmed candidate."""

    with SessionLocal.begin() as session:
        record = session.get(DisruptionCandidateRecord, candidate_id)
        if record is None:
            raise LookupError("Candidate not found")
        if record.review_status != CandidateReviewStatus.ACCEPTED.value:
            raise ValueError("Candidate must be confirmed before analysis")
        record.run_id = run_id
        record.updated_at = datetime.now(timezone.utc)
    return _to_domain(record)


def get_candidate_provenance(candidate_id: str) -> CandidateProvenance:
    """Return the complete evidence chain currently available for a candidate."""

    with SessionLocal() as session:
        candidate = session.get(DisruptionCandidateRecord, candidate_id)
        if candidate is None:
            raise LookupError("Candidate not found")
        document = session.get(RawDocumentRecord, candidate.document_id)
        assessment = session.get(DocumentAssessmentRecord, candidate.document_id)
        version_count = session.scalar(
            select(func.count(CandidateVersionRecord.id)).where(
                CandidateVersionRecord.candidate_id == candidate_id
            )
        ) or 0
    return CandidateProvenance(
        candidate_id=candidate.id,
        source_id=document.source_id,
        document_id=document.id,
        assessment_decision=(
            assessment.human_override or assessment.decision if assessment else None
        ),
        event_id=candidate.event_id,
        confirmed_disruption_id=candidate.confirmed_disruption_id,
        run_id=candidate.run_id,
        version_count=version_count,
    )


def analyze_candidate_exposure(candidate_id: str) -> ExposureAnalysis:
    """Preview structural exposure without creating a real disruption."""

    candidate = get_candidate(candidate_id)
    if candidate is None:
        raise LookupError("Candidate not found")
    if candidate.validation_status is not CandidateValidationStatus.VALIDATED:
        raise ValueError("Only validated candidates have a reliable exposure preview")
    return analyze_exposure(
        Disruption(
            id=candidate.id,
            type=DisruptionType(candidate.disruption_type),
            affected_node_ids=candidate.affected_node_ids,
            affected_edge_ids=candidate.affected_edge_ids,
            start_time=candidate.start_time,
            end_time=candidate.end_time,
            effects=DisruptionEffects.model_validate(candidate.effects),
        )
    )
