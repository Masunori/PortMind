"""PSA-aware document relevance assessment through ``AIProvider``."""

from datetime import datetime, timezone

from app.ai.base import AIProvider
from app.ai.schemas import RelevanceAssessment
from app.database import SessionLocal
from app.domain.assessment import DocumentAssessment, RelevanceDecision
from app.models import DocumentAssessmentRecord, RawDocumentRecord
from app.services.ai_context import build_filter_context


def _to_domain(record: DocumentAssessmentRecord) -> DocumentAssessment:
    """Convert a stored assessment and calculate its effective decision."""

    decision = RelevanceDecision(record.decision)
    override = (
        RelevanceDecision(record.human_override) if record.human_override else None
    )
    return DocumentAssessment(
        document_id=record.document_id,
        decision=decision,
        effective_decision=override or decision,
        relevance_probability=record.relevance_probability,
        rationale=record.rationale,
        matched_entities=record.matched_entities,
        human_override=override,
        assessed_at=record.assessed_at,
        updated_at=record.updated_at,
    )


def _network_context() -> str:
    """Build a compact authoritative context from persisted graph entities."""

    context = build_filter_context()
    return f"Network context version: {context.version}\n{context.text}"


async def assess_document(document_id: str, provider: AIProvider) -> DocumentAssessment:
    """Assess a raw document against current network context and persist it."""

    with SessionLocal() as session:
        document = session.get(RawDocumentRecord, document_id)
        if document is None:
            raise LookupError("Document not found")
        title, content = document.title, document.content
    output = await provider.structured_generate(
        "Assess whether this intelligence can affect the supplied PSA network.\n"
        f"{_network_context()}\nDocument title: {title}\nDocument: {content[:12000]}",
        RelevanceAssessment,
    )
    decision = (
        RelevanceDecision.RELEVANT
        if output.relevance_probability >= 0.7
        else RelevanceDecision.IRRELEVANT
        if output.relevance_probability <= 0.3
        else RelevanceDecision.NEEDS_REVIEW
    )
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        record = session.get(DocumentAssessmentRecord, document_id)
        if record is None:
            record = DocumentAssessmentRecord(
                document_id=document_id,
                human_override=None,
                assessed_at=now,
                updated_at=now,
                decision=decision.value,
                relevance_probability=output.relevance_probability,
                rationale=output.rationale,
                matched_entities=output.matched_entities,
            )
            session.add(record)
        else:
            record.decision = decision.value
            record.relevance_probability = output.relevance_probability
            record.rationale = output.rationale
            record.matched_entities = output.matched_entities
            record.assessed_at = now
            record.updated_at = now
    return _to_domain(record)


def get_assessment(document_id: str) -> DocumentAssessment | None:
    """Return one document assessment or ``None``."""

    with SessionLocal() as session:
        record = session.get(DocumentAssessmentRecord, document_id)
        return _to_domain(record) if record is not None else None


def override_assessment(
    document_id: str, decision: RelevanceDecision | None
) -> DocumentAssessment:
    """Set or clear the human decision without erasing provider evidence."""

    with SessionLocal.begin() as session:
        record = session.get(DocumentAssessmentRecord, document_id)
        if record is None:
            raise LookupError("Assessment not found")
        record.human_override = decision.value if decision else None
        record.updated_at = datetime.now(timezone.utc)
    return _to_domain(record)
