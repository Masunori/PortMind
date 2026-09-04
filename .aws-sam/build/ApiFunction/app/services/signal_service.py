"""Deterministic evidence-to-reviewed-signal workflow orchestration."""

import asyncio
import logging
from app.integrations.contracts import (
    CanonicalSignal, ContextManifest, DisruptionCatalog, DisruptionValidationRequest, EffectMappingRequest,
    EntityResolveRequest, Evidence,
    EvidenceProcessingEligibility, FilterDecision, FilterRequest, FilterResult,
    GroundedEntity, InterpretationProposal, InterpretationRequest,
    RelationshipRequest,
)
from app.integrations.gateway import ClientGateway
from app.integrations.providers import ProviderBundle
from app.integrations.schema_validation import ContractRegistry, validate_payload
from app.repositories import get_signal_repository
from app.repositories.contracts import SignalRepository
from app.repositories.errors import ConflictError, NotFoundError
from app.services.evidence_service import get_evidence

registry = ContractRegistry()
logger = logging.getLogger(__name__)

def _repo(repository: SignalRepository | None = None) -> SignalRepository:
    return repository or get_signal_repository()


def _load_evidence(evidence_id: str) -> Evidence:
    evidence = get_evidence(evidence_id)
    if evidence is None: raise LookupError("Evidence not found")
    return evidence


def get_evidence_processing_eligibility(
    evidence_id: str, repository: SignalRepository | None = None,
) -> EvidenceProcessingEligibility:
    """Allow a new candidate only when every prior attempt was rejected."""

    if get_evidence(evidence_id) is None:
        raise LookupError("Evidence not found")
    attempts = list(_repo(repository).attempts(evidence_id))
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
                           providers: ProviderBundle, repository: SignalRepository | None = None) -> FilterResult:
    assessment = await providers.filter.assess(FilterRequest(
        evidence=evidence, model_context=context.compact_context, context_version=context.context_version))
    _repo(repository).save_assessment(evidence.id, assessment, context.context_version)
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
                              retry_of_signal_id: str | None = None,
                              repository: SignalRepository | None = None) -> str:
    return _repo(repository).create_candidate(evidence, proposal, context.context_version, retry_of_signal_id)


async def _ground_entities(version_id: str, proposal: InterpretationProposal,
                           context: ContextManifest, *, gateway: ClientGateway,
                           repository: SignalRepository | None = None) -> list[GroundedEntity]:
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
        _repo(repository).add_entity(version_id, item)
    return grounded


async def _map_and_validate_effect(version_id: str, proposal: InterpretationProposal,
                                   grounded: list[GroundedEntity], context: ContextManifest, *,
                                   catalog: DisruptionCatalog, gateway: ClientGateway,
                                   providers: ProviderBundle,
                                   repository: SignalRepository | None = None) -> float | None:
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
    _repo(repository).add_effect(version_id, outcome=outcome, errors=errors,
        mapping_proposal=mapping_data, local_validation=local_validation,
        client_validation=client_validation, normalized_disruption=normalized,
        catalog_version=catalog_version, schema_hash=schema_hash,
        context_version=context.context_version)
    return mapping_confidence


def _persist_unexpected_mapping_failure(
    version_id: str, context: ContextManifest, repository: SignalRepository | None = None,
) -> None:
    """Make an interrupted synchronous mapping attempt visibly terminal."""

    _repo(repository).add_effect(version_id, outcome="PROCESSING_FAILED",
        errors=["Mapping failed unexpectedly; reject and reprocess this signal"],
        mapping_proposal={}, local_validation={"valid":False,"errors":[]},
        client_validation={"valid":False,"errors":[]}, normalized_disruption=None,
        catalog_version="", schema_hash="", context_version=context.context_version)


def _finalize_signal(version_id: str, grounded: list[GroundedEntity],
                     mapping_confidence: float | None,
                     repository: SignalRepository | None = None) -> CanonicalSignal:
    grounding_confidence = min(
        (item.confidence for item in grounded if item.is_target), default=0)
    return _repo(repository).finalize(version_id, grounding_confidence, mapping_confidence)


async def process_evidence(evidence_id: str, *, gateway: ClientGateway,
                           providers: ProviderBundle,
                           repository: SignalRepository | None = None) -> CanonicalSignal | None:
    """Filter, interpret, ground, map, and validate one normalized evidence item."""

    evidence = _load_evidence(evidence_id)
    eligibility = get_evidence_processing_eligibility(evidence_id, repository)
    if not eligibility.can_process:
        raise ValueError(
            "Evidence cannot be reprocessed while a prior signal is pending or accepted"
        )
    context = await gateway.get_context()
    assessment = await _assess_evidence(evidence, context, providers=providers, repository=repository)
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
        retry_of_signal_id=eligibility.retry_of_signal_id, repository=repository,
    )
    _repo(repository).set_processing_state(version_id, "GROUNDING_PENDING")
    grounded = await _ground_entities(version_id, proposal, context, gateway=gateway, repository=repository)
    _repo(repository).set_processing_state(version_id, "MAPPING_PENDING")
    try:
        mapping_confidence = await _map_and_validate_effect(
            version_id, proposal, grounded, context, catalog=catalog,
            gateway=gateway, providers=providers, repository=repository)
    except Exception:
        logger.exception("Unexpected mapping failure for signal version %s", version_id)
        _persist_unexpected_mapping_failure(version_id, context, repository)
        mapping_confidence = None
    return _finalize_signal(version_id, grounded, mapping_confidence, repository)


def get_signal_version(version_id: str, repository: SignalRepository | None = None) -> CanonicalSignal:
    try:return _repo(repository).get_version(version_id)
    except NotFoundError as error:raise LookupError(str(error)) from error


def list_signals(*, review_status: str | None = None, limit: int = 50,
                 offset: int = 0, repository: SignalRepository | None = None) -> list[CanonicalSignal]:
    """Return current signal versions, optionally filtered by review state."""

    repo=_repo(repository);token=None;skipped=0
    while True:
        page=repo.list(review_status=review_status,limit=min(1000,offset+limit),continuation_token=token)
        if skipped+len(page.items)>offset or page.continuation_token is None:
            start=max(0,offset-skipped);return list(page.items[start:start+limit])
        skipped+=len(page.items);token=page.continuation_token


def review_signal(signal_id: str, decision: str, repository: SignalRepository | None = None,
                  *, expected_version: int | None = None) -> CanonicalSignal:
    """Accept or reject a candidate without mutating its immutable version."""

    if decision not in {"ACCEPTED", "REJECTED"}: raise ValueError("Unsupported review decision")
    try:return _repo(repository).review(signal_id,decision,expected_version=expected_version)
    except NotFoundError as error:raise LookupError(str(error)) from error
    except ConflictError as error:raise ValueError(str(error)) from error


async def relate_signals(source_version_id: str, target_version_id: str, *,
                         providers: ProviderBundle,
                         repository: SignalRepository | None = None) -> dict[str, object] | None:
    """Persist a provider proposal; downstream enforcement remains deterministic."""

    if source_version_id == target_version_id: raise ValueError("A signal cannot relate to itself")
    source = get_signal_version(source_version_id,repository); target = get_signal_version(target_version_id,repository)
    proposal = await providers.relationship.propose_relationship(RelationshipRequest(
        source_signal_version_id=source_version_id, target_signal_version_id=target_version_id,
        source_summary=f"{source.signal_type}:{source.entities}",
        target_summary=f"{target.signal_type}:{target.entities}"))
    if proposal.relationship is None: return None
    return _repo(repository).relate(source_version_id,target_version_id,
        relationship=proposal.relationship.value,confidence=proposal.confidence,
        rationale=proposal.rationale)
