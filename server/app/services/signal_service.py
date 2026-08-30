"""Deterministic evidence-to-reviewed-signal workflow orchestration."""

import asyncio
from datetime import datetime, timezone
import logging
from uuid import uuid4

from sqlalchemy import func, select

from app.database import SessionLocal
from app.integrations.contracts import (
    CanonicalSignal, ContextManifest, DisruptionCatalog, DisruptionValidationRequest, EffectMappingRequest,
    EntityResolveRequest, Evidence, EvidenceProcessingAttempt,
    EvidenceProcessingEligibility, FilterDecision, FilterRequest, FilterResult,
    GroundedEntity, InterpretationProposal, InterpretationRequest, ProviderMetadata,
    RelationshipRequest, SignalClass, TemporalWindow,
)
from app.integrations.gateway import ClientGateway
from app.integrations.providers import ProviderBundle
from app.integrations.schema_validation import ContractRegistry, validate_payload
from app.models import (
    EvidenceAssessmentRecord, SignalEffectRecord, SignalEntityRecord, SignalEvidenceRecord,
    SignalRecord, SignalVersionRecord,
    SignalRelationshipRecord,
)
from app.services.evidence_service import get_evidence

registry = ContractRegistry()
logger = logging.getLogger(__name__)


def _load_evidence(evidence_id: str) -> Evidence:
    evidence = get_evidence(evidence_id)
    if evidence is None: raise LookupError("Evidence not found")
    return evidence


def get_evidence_processing_eligibility(
    evidence_id: str,
) -> EvidenceProcessingEligibility:
    """Allow a new candidate only when every prior attempt was rejected."""

    if get_evidence(evidence_id) is None:
        raise LookupError("Evidence not found")
    with SessionLocal() as session:
        rows = session.execute(
            select(SignalRecord, SignalVersionRecord)
            .join(SignalVersionRecord, SignalVersionRecord.signal_id == SignalRecord.id)
            .join(SignalEvidenceRecord,
                  SignalEvidenceRecord.signal_version_id == SignalVersionRecord.id)
            .where(SignalEvidenceRecord.evidence_id == evidence_id,
                   SignalRecord.current_version_id == SignalVersionRecord.id)
            .order_by(SignalRecord.created_at, SignalRecord.id)
        ).all()
    attempts = [EvidenceProcessingAttempt(
        signal_id=signal.id, signal_version_id=version.id,
        signal_type=version.signal_type,
        retry_of_signal_id=signal.retry_of_signal_id,
        review_status=signal.review_status,
        processing_state=version.processing_state,
        created_at=signal.created_at,
    ) for signal, version in rows]
    blockers = sorted({attempt.review_status for attempt in attempts
                       if attempt.review_status != "REJECTED"})
    can_process = not blockers
    retry_of = attempts[-1].signal_id if attempts and can_process else None
    return EvidenceProcessingEligibility(
        evidence_id=evidence_id, can_process=can_process,
        retry_of_signal_id=retry_of,
        blocked_by=[f"signal_{status.casefold()}" for status in blockers],
        attempts=attempts,
    )


async def _assess_evidence(evidence: Evidence, context: ContextManifest, *,
                           providers: ProviderBundle) -> FilterResult:
    assessment = await providers.filter.assess(FilterRequest(
        evidence=evidence, model_context=context.compact_context, context_version=context.context_version))
    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        session.add(EvidenceAssessmentRecord(id=f"assessment-{uuid4().hex}", evidence_id=evidence.id,
            decision=assessment.decision.value, relevance_probability=assessment.relevance_probability,
            reason_codes=assessment.reason_codes, rationale=assessment.rationale, entity_hints=assessment.entity_hints,
            provider_metadata=assessment.metadata.model_dump(mode="json"), context_version=context.context_version,
            human_override=None, created_at=now))
    return assessment


async def _interpret_evidence(evidence: Evidence, context: ContextManifest, *,
                              capabilities: dict[str, object], catalog: DisruptionCatalog,
                              providers: ProviderBundle) -> InterpretationProposal:
    return await providers.interpreter.interpret(InterpretationRequest(
        evidence=evidence, context_version=context.context_version,
        entity_resolution_capabilities=capabilities,
        disruption_contracts=[{
            "type": contract.type,
            "target_types": contract.target_types,
            "payload_schema": contract.payload_schema,
        } for contract in catalog.contracts]))


def _persist_candidate_signal(evidence: Evidence, proposal: InterpretationProposal,
                              context: ContextManifest, *,
                              retry_of_signal_id: str | None = None) -> str:
    now = datetime.now(timezone.utc)
    signal_id = f"signal-{uuid4().hex}"; version_id = f"{signal_id}-v1"
    with SessionLocal.begin() as session:
        session.add(SignalRecord(id=signal_id, retry_of_signal_id=retry_of_signal_id,
            current_version_id=version_id, lifecycle_status="CANDIDATE",
            review_status="PENDING", expires_at=None, retention_class=evidence.retention_class.value, created_at=now))
        # These records are linked by identifier rather than ORM relationships, so
        # make the database dependency order explicit before adding child rows.
        session.flush()
        session.add(SignalVersionRecord(id=version_id, signal_id=signal_id, version=1,
            classification=proposal.classification.value, signal_type=proposal.signal_type,
            temporal_window=proposal.temporal_window.model_dump(mode="json"),
            occurrence_probability=proposal.occurrence_probability, severity=proposal.severity,
            extraction_confidence=proposal.extraction_confidence, grounding_confidence=None,
            mapping_confidence=None, processing_state="INTERPRETED",
            provider_metadata=proposal.metadata.model_dump(mode="json"),
            context_version=context.context_version, created_at=now))
        session.flush()
        for supporting_id in proposal.supporting_evidence_ids:
            session.add(SignalEvidenceRecord(signal_version_id=version_id, evidence_id=supporting_id))
    return version_id


async def _ground_entities(version_id: str, proposal: InterpretationProposal,
                           context: ContextManifest, *, gateway: ClientGateway) -> list[GroundedEntity]:
    grounded: list[GroundedEntity] = []
    targets = {mention.casefold() for mention in proposal.target_entity_mentions}
    mentions = list(dict.fromkeys(proposal.entity_mentions))
    for mention in mentions:
        resolution = await gateway.resolve_entity(EntityResolveRequest(
            mention=mention, context_version=context.context_version))
        item = GroundedEntity(mention=mention, is_target=mention.casefold() in targets,
            status=resolution.status.value,
            entity_id=resolution.entity.entity_id if resolution.entity else None,
            entity_type=resolution.entity.entity_type if resolution.entity else None,
            method=resolution.method, confidence=resolution.confidence,
            context_version=resolution.context_version)
        grounded.append(item)
        with SessionLocal.begin() as session:
            session.add(SignalEntityRecord(signal_version_id=version_id, mention=item.mention,
                is_target=item.is_target,
                entity_id=item.entity_id, entity_type=item.entity_type, status=item.status, method=item.method,
                confidence=item.confidence, context_version=item.context_version))
    return grounded


async def _map_and_validate_effect(version_id: str, proposal: InterpretationProposal,
                                   grounded: list[GroundedEntity], context: ContextManifest, *,
                                   catalog: DisruptionCatalog, gateway: ClientGateway,
                                   providers: ProviderBundle) -> float | None:
    normalized = None; mapping_confidence = None
    outcome = "MAPPED"; errors: list[str] = []; mapping_data = {}
    local_validation = {"valid": False, "errors": []}; client_validation = {"valid": False, "errors": []}
    catalog_version = ""; schema_hash = ""
    contract = None
    targets = [item for item in grounded if item.is_target]
    if not targets:
        outcome = "NO_ENTITIES"; errors = ["Signal contains no target entity mentions"]
    elif any(item.status != "RESOLVED" for item in targets):
        outcome = "UNRESOLVED_ENTITIES"
        errors = [f"{item.mention}: {item.status}" for item in targets
                  if item.status != "RESOLVED"]
    else:
        registry.register(context.client_id, catalog)
        catalog_version = catalog.catalog_version
        contract = next((item for item in catalog.contracts if item.type == proposal.signal_type), None)
        if outcome == "MAPPED" and contract is None:
            outcome = "UNSUPPORTED_SIGNAL_TYPE"; errors = [f"Unsupported signal type: {proposal.signal_type}"]
        if outcome == "MAPPED" and contract is not None:
            schema_hash = contract.schema_hash
            allowed = {value.casefold() for value in contract.target_types}
            incompatible = [item for item in targets
                            if not item.entity_type or item.entity_type.casefold() not in allowed]
            if incompatible:
                outcome = "LOCAL_VALIDATION_FAILED"
                errors = [f"{item.mention}: entity type {item.entity_type!r} is not one of {contract.target_types}"
                          for item in incompatible]
            else:
                mapping = await providers.effect_mapping.propose_mapping(EffectMappingRequest(
                    signal_version_id=version_id, signal_type=proposal.signal_type,
                    resolved_entity_ids=[item.entity_id for item in targets if item.entity_id],
                    severity=proposal.severity, temporal_window=proposal.temporal_window,
                    contract=contract, context_version=context.context_version))
                mapping_data = mapping.model_dump(mode="json"); mapping_confidence = mapping.mapping_confidence
                errors = validate_payload(mapping.payload, contract.payload_schema)
                local_validation = {"valid": not errors, "errors": errors}
                if errors:
                    outcome = "LOCAL_VALIDATION_FAILED"
                else:
                    try:
                        client_result = await gateway.validate_disruption(DisruptionValidationRequest(
                            disruption_type=mapping.disruption_type, payload=mapping.payload,
                            catalog_version=catalog_version, context_version=context.context_version,
                            schema_hash=contract.schema_hash))
                        client_validation = client_result.model_dump(mode="json")
                        if client_result.valid:
                            normalized = client_result.normalized_payload
                        else:
                            outcome = "CLIENT_VALIDATION_FAILED"; errors = client_result.errors
                    except Exception as exc:
                        outcome = "CLIENT_UNAVAILABLE"; errors = [str(exc)]
    if not local_validation["errors"] and outcome == "LOCAL_VALIDATION_FAILED":
        local_validation = {"valid": False, "errors": errors}
    with SessionLocal.begin() as session:
        session.add(SignalEffectRecord(id=f"effect-{uuid4().hex}", signal_version_id=version_id,
            outcome=outcome, errors=errors, mapping_proposal=mapping_data,
            local_validation=local_validation, client_validation=client_validation,
            normalized_disruption=normalized, catalog_version=catalog_version, schema_hash=schema_hash,
            context_version=context.context_version, created_at=datetime.now(timezone.utc)))
    return mapping_confidence


def _persist_unexpected_mapping_failure(
    version_id: str, context: ContextManifest,
) -> None:
    """Make an interrupted synchronous mapping attempt visibly terminal."""

    with SessionLocal.begin() as session:
        session.add(SignalEffectRecord(
            id=f"effect-{uuid4().hex}", signal_version_id=version_id,
            outcome="PROCESSING_FAILED",
            errors=["Mapping failed unexpectedly; reject and reprocess this signal"],
            mapping_proposal={}, local_validation={"valid": False, "errors": []},
            client_validation={"valid": False, "errors": []},
            normalized_disruption=None, catalog_version="", schema_hash="",
            context_version=context.context_version,
            created_at=datetime.now(timezone.utc),
        ))


def _finalize_signal(version_id: str, grounded: list[GroundedEntity],
                     mapping_confidence: float | None) -> CanonicalSignal:
    grounding_confidence = min(
        (item.confidence for item in grounded if item.is_target), default=0)
    with SessionLocal.begin() as session:
        version = session.get(SignalVersionRecord, version_id)
        version.grounding_confidence = grounding_confidence; version.mapping_confidence = mapping_confidence
        effect = session.scalar(select(SignalEffectRecord).where(
            SignalEffectRecord.signal_version_id == version_id).order_by(SignalEffectRecord.created_at.desc()))
        version.processing_state = "READY_FOR_REVIEW" if effect and effect.outcome == "MAPPED" else (
            "NEEDS_RESOLUTION" if effect and effect.outcome in {"NO_ENTITIES", "UNRESOLVED_ENTITIES"}
            else "MAPPING_FAILED")
    return get_signal_version(version_id)


async def process_evidence(evidence_id: str, *, gateway: ClientGateway,
                           providers: ProviderBundle) -> CanonicalSignal | None:
    """Filter, interpret, ground, map, and validate one normalized evidence item."""

    evidence = _load_evidence(evidence_id)
    eligibility = get_evidence_processing_eligibility(evidence_id)
    if not eligibility.can_process:
        raise ValueError(
            "Evidence cannot be reprocessed while a prior signal is pending or accepted"
        )
    context = await gateway.get_context()
    assessment = await _assess_evidence(evidence, context, providers=providers)
    if assessment.decision != FilterDecision.ACCEPT: return None

    capabilities, catalog = await asyncio.gather(
        gateway.get_entity_resolution_capabilities(),
        gateway.get_disruption_contracts(),
    )
    proposal = await _interpret_evidence(
        evidence, context, capabilities=capabilities.manifest, catalog=catalog,
        providers=providers)
    version_id = _persist_candidate_signal(
        evidence, proposal, context,
        retry_of_signal_id=eligibility.retry_of_signal_id,
    )
    with SessionLocal.begin() as session:
        session.get(SignalVersionRecord, version_id).processing_state = "GROUNDING_PENDING"
    grounded = await _ground_entities(version_id, proposal, context, gateway=gateway)
    with SessionLocal.begin() as session:
        session.get(SignalVersionRecord, version_id).processing_state = "MAPPING_PENDING"
    try:
        mapping_confidence = await _map_and_validate_effect(
            version_id, proposal, grounded, context, catalog=catalog,
            gateway=gateway, providers=providers)
    except Exception:
        logger.exception("Unexpected mapping failure for signal version %s", version_id)
        _persist_unexpected_mapping_failure(version_id, context)
        mapping_confidence = None
    return _finalize_signal(version_id, grounded, mapping_confidence)


def get_signal_version(version_id: str) -> CanonicalSignal:
    with SessionLocal() as session:
        version = session.get(SignalVersionRecord, version_id)
        if version is None: raise LookupError("Signal version not found")
        signal = session.get(SignalRecord, version.signal_id)
        evidence_ids = list(session.scalars(select(SignalEvidenceRecord.evidence_id).where(
            SignalEvidenceRecord.signal_version_id == version_id)))
        entity_records = session.scalars(select(SignalEntityRecord).where(
            SignalEntityRecord.signal_version_id == version_id).order_by(SignalEntityRecord.id)).all()
        effect = session.scalar(select(SignalEffectRecord).where(SignalEffectRecord.signal_version_id == version_id)
                                .order_by(SignalEffectRecord.created_at.desc()))
        
    return CanonicalSignal(id=version.id, signal_id=version.signal_id,
        retry_of_signal_id=signal.retry_of_signal_id, version=version.version,
        classification=version.classification, signal_type=version.signal_type,
        temporal_window=TemporalWindow.model_validate(version.temporal_window),
        occurrence_probability=version.occurrence_probability, severity=version.severity,
        extraction_confidence=version.extraction_confidence, grounding_confidence=version.grounding_confidence,
        mapping_confidence=version.mapping_confidence, evidence_ids=evidence_ids,
        entities=[GroundedEntity(mention=e.mention, is_target=e.is_target,
            status=e.status, entity_id=e.entity_id,
            entity_type=e.entity_type, method=e.method, confidence=e.confidence,
            context_version=e.context_version) for e in entity_records],
        provider_metadata=ProviderMetadata.model_validate(version.provider_metadata),
        context_version=version.context_version, lifecycle_status=signal.lifecycle_status,
        review_status=signal.review_status, processing_state=version.processing_state,
        mapping_outcome=effect.outcome if effect else None, mapping_errors=effect.errors if effect else [],
        normalized_disruption=effect.normalized_disruption if effect else None)


def list_signals(*, review_status: str | None = None, limit: int = 50,
                 offset: int = 0) -> list[CanonicalSignal]:
    """Return current signal versions, optionally filtered by review state."""

    with SessionLocal() as session:
        query = select(SignalRecord).order_by(SignalRecord.created_at.desc())
        if review_status is not None:
            query = query.where(SignalRecord.review_status == review_status)
        version_ids = [record.current_version_id for record in session.scalars(
            query.limit(limit).offset(offset))]
    return [get_signal_version(version_id) for version_id in version_ids]


def review_signal(signal_id: str, decision: str) -> CanonicalSignal:
    """Accept or reject a candidate without mutating its immutable version."""

    if decision not in {"ACCEPTED", "REJECTED"}: raise ValueError("Unsupported review decision")
    with SessionLocal.begin() as session:
        signal = session.get(SignalRecord, signal_id)
        if signal is None: raise LookupError("Signal not found")
        if decision == "ACCEPTED":
            effect = session.scalar(select(SignalEffectRecord).where(
                SignalEffectRecord.signal_version_id == signal.current_version_id))
            entities = session.scalars(select(SignalEntityRecord).where(
                SignalEntityRecord.signal_version_id == signal.current_version_id)).all()
            if any(item.status != "RESOLVED" for item in entities): raise ValueError("All entities must be resolved")
            if effect is None or effect.normalized_disruption is None: raise ValueError("Client-normalized disruption is required")
        signal.review_status = decision; signal.lifecycle_status = "ACTIVE" if decision == "ACCEPTED" else "REJECTED"
        version_id = signal.current_version_id
    return get_signal_version(version_id)


async def relate_signals(source_version_id: str, target_version_id: str, *,
                         providers: ProviderBundle) -> dict[str, object] | None:
    """Persist a provider proposal; downstream enforcement remains deterministic."""

    if source_version_id == target_version_id: raise ValueError("A signal cannot relate to itself")
    source = get_signal_version(source_version_id); target = get_signal_version(target_version_id)
    proposal = await providers.relationship.propose_relationship(RelationshipRequest(
        source_signal_version_id=source_version_id, target_signal_version_id=target_version_id,
        source_summary=f"{source.signal_type}:{source.entities}",
        target_summary=f"{target.signal_type}:{target.entities}"))
    if proposal.relationship is None: return None
    now = datetime.now(timezone.utc); relationship_id = f"relationship-{uuid4().hex}"
    with SessionLocal.begin() as session:
        session.add(SignalRelationshipRecord(id=relationship_id,
            source_signal_version_id=source_version_id, target_signal_version_id=target_version_id,
            relationship=proposal.relationship.value, confidence=proposal.confidence,
            rationale=proposal.rationale, created_at=now))
    return {"id": relationship_id, **proposal.model_dump(mode="json")}
