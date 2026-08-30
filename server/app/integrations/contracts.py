"""Versioned integration contracts shared by gateways and provider boundaries.

These models deliberately contain no persistence or vendor-specific behavior.  All
exchange envelopes reject unknown fields so contract drift fails at the boundary.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Probability = Annotated[float, Field(ge=0, le=1)]


class ContractModel(BaseModel):
    """Base for strict external exchange objects."""

    model_config = ConfigDict(extra="forbid")


class EvidenceKind(str, Enum):
    """Describe how an evidence item entered the platform."""

    UPLOAD = "UPLOAD"
    WEBSITE = "WEBSITE"
    RSS = "RSS"
    API = "API"
    STRUCTURED = "STRUCTURED"
    MANUAL = "MANUAL"
    LARGE_CONTENT_REFERENCE = "LARGE_CONTENT_REFERENCE"


class ProcessingStatus(str, Enum):
    """Track progress of collection or evidence processing."""

    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class RetentionClass(str, Enum):
    """Define the lifecycle and deletion policy applied to evidence."""

    TRANSIENT = "TRANSIENT"
    STANDARD = "STANDARD"
    AUDIT = "AUDIT"
    LEGAL_HOLD = "LEGAL_HOLD"


class Evidence(ContractModel):
    """Normalized structured or unstructured evidence envelope."""

    id: str
    source_id: str
    collection_run_id: str | None = None
    kind: EvidenceKind
    title: str = Field(min_length=1, max_length=500)
    media_type: str = Field(min_length=1, max_length=200)
    content: str | None = None
    structured_content: dict[str, Any] | list[Any] | None = None
    content_reference: str | None = None
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    duplicate_of_id: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    processed_at: datetime | None = None
    processing_status: ProcessingStatus
    parser_warnings: list[str] = Field(default_factory=list, max_length=100)
    quality_metadata: dict[str, Any] = Field(default_factory=dict)
    retention_class: RetentionClass = RetentionClass.STANDARD
    expires_at: datetime | None = None
    archived_at: datetime | None = None

    @model_validator(mode="after")
    def require_content(self) -> "Evidence":
        if (self.content is None and self.structured_content is None
                and self.content_reference is None and self.duplicate_of_id is None):
            raise ValueError("Evidence requires content, structured_content, or content_reference")
        if self.duplicate_of_id == self.id:
            raise ValueError("Evidence cannot duplicate itself")
        return self


class EvidenceCreate(ContractModel):
    """Fields accepted by the normalized evidence ingestion service."""

    source_id: str
    collection_run_id: str | None = None
    kind: EvidenceKind
    title: str = Field(min_length=1, max_length=500)
    media_type: str = Field(min_length=1, max_length=200)
    content: str | None = None
    structured_content: dict[str, Any] | list[Any] | None = None
    content_reference: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    collected_at: datetime | None = None
    parser_warnings: list[str] = Field(default_factory=list, max_length=100)
    quality_metadata: dict[str, Any] = Field(default_factory=dict)
    processing_status: ProcessingStatus = ProcessingStatus.COMPLETE
    retention_class: RetentionClass = RetentionClass.STANDARD
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def require_content(self) -> "EvidenceCreate":
        if self.content is None and self.structured_content is None and self.content_reference is None:
            raise ValueError("Evidence requires content, structured_content, or content_reference")
        return self


class EvidenceUpdate(ContractModel):
    """Editable fields for evidence that has not entered an audit workflow."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = None
    content_reference: str | None = None
    source_url: str | None = None
    quality_metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "EvidenceUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one evidence field must be supplied")
        return self


class EvidenceStoreResult(ContractModel):
    """Return stored evidence and whether it duplicated existing content."""

    evidence: Evidence
    duplicate: bool


class DeletionImpact(ContractModel):
    """Explain which destructive evidence operations are currently allowed."""

    evidence_id: str
    can_remove_raw_content: bool
    can_delete_permanently: bool
    protected_by: list[str]
    raw_content_present: bool


class DuplicateDeletionCandidate(ContractModel):
    evidence_id: str
    can_delete: bool
    protected_by: list[str] = Field(default_factory=list)


class DuplicateDeletionPreview(ContractModel):
    canonical_evidence_id: str
    candidates: list[DuplicateDeletionCandidate]


class DuplicateDeletionResult(ContractModel):
    canonical_evidence_id: str
    deleted_ids: list[str]
    skipped: list[DuplicateDeletionCandidate]
    canonical_deleted: bool = False


class CollectionBatch(ContractModel):
    """Group related collection runs under a user-facing label."""

    id: str
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    created_at: datetime


class CollectionRun(ContractModel):
    """Report the lifecycle and outcome counts of one collection attempt."""

    id: str
    batch_id: str | None = None
    source_id: str | None = None
    status: ProcessingStatus
    started_at: datetime
    completed_at: datetime | None = None
    accepted_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)


class ProviderMetadata(ContractModel):
    """Record the provider invocation needed to reproduce an AI proposal."""

    provider: str
    model: str
    prompt_version: str
    request_id: str | None = None
    stub: bool = False


class FilterDecision(str, Enum):
    """Enumerate evidence triage outcomes returned by a filter provider."""

    ACCEPT = "ACCEPT"
    REVIEW = "REVIEW"
    REJECT = "REJECT"
    QUARANTINE = "QUARANTINE"


class FilterRequest(ContractModel):
    """Supply evidence and versioned client context for relevance filtering."""

    evidence: Evidence
    model_context: dict[str, Any]
    context_version: str


class FilterResult(ContractModel):
    """Capture a provider's evidence triage decision and its provenance."""

    decision: FilterDecision
    relevance_probability: Probability
    reason_codes: list[str]
    rationale: str
    entity_hints: list[str]
    metadata: ProviderMetadata


class SignalClass(str, Enum):
    """Distinguish reported events, forecasts, and user hypotheticals."""

    OBSERVED = "OBSERVED"
    FORECAST = "FORECAST"
    HYPOTHETICAL = "HYPOTHETICAL"


class SignalProcessingState(str, Enum):
    """Track an accepted candidate through grounding and effect mapping."""

    INTERPRETED = "INTERPRETED"
    GROUNDING_PENDING = "GROUNDING_PENDING"
    MAPPING_PENDING = "MAPPING_PENDING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    NEEDS_RESOLUTION = "NEEDS_RESOLUTION"
    MAPPING_FAILED = "MAPPING_FAILED"


class MappingOutcome(str, Enum):
    """Describe the terminal result of one effect-mapping attempt."""

    MAPPED = "MAPPED"
    NO_ENTITIES = "NO_ENTITIES"
    UNRESOLVED_ENTITIES = "UNRESOLVED_ENTITIES"
    UNSUPPORTED_SIGNAL_TYPE = "UNSUPPORTED_SIGNAL_TYPE"
    LOCAL_VALIDATION_FAILED = "LOCAL_VALIDATION_FAILED"
    CLIENT_VALIDATION_FAILED = "CLIENT_VALIDATION_FAILED"
    CLIENT_UNAVAILABLE = "CLIENT_UNAVAILABLE"
    PROCESSING_FAILED = "PROCESSING_FAILED"


class TemporalWindow(ContractModel):
    """Represent an optional half-open time window for a signal."""

    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def ordered(self) -> "TemporalWindow":
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class InterpreterDisruptionContract(ContractModel):
    """Bounded client capability exposed to an untrusted interpreter."""

    type: str
    target_types: list[str]
    payload_schema: dict[str, Any]


class InterpretationRequest(ContractModel):
    """Request extraction of a proposed signal from canonical evidence."""

    evidence: Evidence
    context_version: str
    entity_resolution_capabilities: dict[str, Any] = Field(default_factory=dict)
    disruption_contracts: list[InterpreterDisruptionContract] = Field(min_length=1)


class InterpretationProposal(ContractModel):
    """Describe an ungrounded signal proposed by an interpreter provider."""

    classification: SignalClass
    signal_type: str
    entity_mentions: list[str]
    target_entity_mentions: list[str]
    temporal_window: TemporalWindow
    occurrence_probability: Probability
    severity: Probability
    extraction_confidence: Probability
    supporting_evidence_ids: list[str]
    metadata: ProviderMetadata

    @model_validator(mode="after")
    def evidence_semantics(self) -> "InterpretationProposal":
        if self.classification == SignalClass.HYPOTHETICAL and self.supporting_evidence_ids:
            raise ValueError("Hypothetical signals cannot claim supporting evidence")
        mentions = {item.casefold() for item in self.entity_mentions}
        if any(item.casefold() not in mentions for item in self.target_entity_mentions):
            raise ValueError("Target entity mentions must be included in entity mentions")
        return self


class GroundedEntity(ContractModel):
    """Record how one textual mention maps to the client's entity model."""

    mention: str
    is_target: bool = False
    status: str
    entity_id: str | None = None
    entity_type: str | None = None
    method: str
    confidence: Probability
    context_version: str


class CanonicalSignal(ContractModel):
    """One immutable signal version exposed to review and scenario workflows."""

    id: str
    signal_id: str
    retry_of_signal_id: str | None = None
    version: int = Field(ge=1)
    classification: SignalClass
    signal_type: str
    temporal_window: TemporalWindow
    occurrence_probability: Probability
    severity: Probability
    extraction_confidence: Probability
    grounding_confidence: Probability | None = None
    mapping_confidence: Probability | None = None
    evidence_ids: list[str]
    entities: list[GroundedEntity]
    provider_metadata: ProviderMetadata
    context_version: str
    lifecycle_status: str
    review_status: str
    processing_state: SignalProcessingState
    mapping_outcome: MappingOutcome | None = None
    mapping_errors: list[str] = Field(default_factory=list)
    normalized_disruption: dict[str, Any] | None = None


class EvidenceProcessingAttempt(ContractModel):
    """Summarize one immutable signal attempt derived from evidence."""

    signal_id: str
    signal_version_id: str
    signal_type: str
    retry_of_signal_id: str | None = None
    review_status: str
    processing_state: SignalProcessingState
    created_at: datetime


class EvidenceProcessingEligibility(ContractModel):
    """Explain whether stored evidence may produce another signal candidate."""

    evidence_id: str
    can_process: bool
    retry_of_signal_id: str | None = None
    blocked_by: list[str] = Field(default_factory=list)
    attempts: list[EvidenceProcessingAttempt] = Field(default_factory=list)


class EntityStatus(str, Enum):
    """Describe the outcome of resolving an entity mention."""

    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED_TYPE = "UNSUPPORTED_TYPE"
    STALE_CONTEXT = "STALE_CONTEXT"


class EntityCandidate(ContractModel):
    """Represent one authoritative client entity search candidate."""

    entity_id: str
    entity_type: str
    display_name: str
    confidence: Probability


class EntitySearchRequest(ContractModel):
    """Search the current client context for matching entities."""

    query: str = Field(default="", max_length=300)
    entity_types: list[str] = Field(default_factory=list)
    context_version: str
    limit: int = Field(default=10, ge=1, le=50)


class EntitySearchResponse(ContractModel):
    """Return entity candidates tied to the context used for the search."""

    candidates: list[EntityCandidate]
    context_version: str


class EntityResolveRequest(ContractModel):
    """Resolve a mention, optionally constrained to a selected candidate."""

    mention: str = Field(min_length=1, max_length=300)
    candidate_id: str | None = None
    entity_type: str | None = None
    context_version: str


class EntityResolution(ContractModel):
    """Return the authoritative resolution status for one mention."""

    status: EntityStatus
    context_version: str
    entity: EntityCandidate | None = None
    candidates: list[EntityCandidate] = Field(default_factory=list)
    method: str
    confidence: Probability


class EntityResolutionCapabilities(ContractModel):
    """Validated envelope for client-advertised entity extraction guidance."""

    contract_version: str
    entity_registry_version: str
    manifest: dict[str, Any]


class ContextManifest(ContractModel):
    """Version stamp and compact metadata for the connected client model."""

    client_id: str
    context_version: str
    schema_version: str
    capability_version: str
    state_version: str
    generated_at: datetime
    compact_context: dict[str, Any] = Field(default_factory=dict)


class ModelSchemaResponse(ContractModel):
    """Expose the client's versioned model schema document."""

    schema_version: str
    context_version: str
    schema_document: dict[str, Any]


class StateQueryRequest(ContractModel):
    """Request selected fields for a bounded set of client entities."""

    entity_ids: list[str] = Field(min_length=1, max_length=100)
    fields: list[str] = Field(min_length=1, max_length=20)
    context_version: str


class StateQueryResponse(ContractModel):
    """Return authoritative entity state with context and state versions."""

    context_version: str
    state_version: str
    records: list[dict[str, Any]]


class DisruptionContract(ContractModel):
    """Define one client-supported disruption type and payload schema."""

    type: str
    target_types: list[str]
    payload_schema: dict[str, Any]
    schema_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class DisruptionCatalog(ContractModel):
    """List versioned disruption contracts advertised by the client."""

    catalog_version: str
    context_version: str
    capability_version: str
    contracts: list[DisruptionContract]


class DisruptionValidationRequest(ContractModel):
    """Ask the client to validate a proposed disruption payload."""

    disruption_type: str
    payload: dict[str, Any]
    catalog_version: str
    context_version: str
    schema_hash: str


class DisruptionValidationResponse(ContractModel):
    """Return validation errors and the client's normalized payload."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    normalized_payload: dict[str, Any] | None = None
    catalog_version: str
    context_version: str


class EffectMappingRequest(ContractModel):
    """Provide a grounded signal and target contract for effect mapping."""

    signal_version_id: str
    signal_type: str
    resolved_entity_ids: list[str]
    severity: Probability
    temporal_window: TemporalWindow
    contract: DisruptionContract
    context_version: str


class EffectMappingProposal(ContractModel):
    """Capture a provider-proposed disruption and mapping confidence."""

    disruption_type: str
    payload: dict[str, Any]
    mapping_confidence: Probability
    metadata: ProviderMetadata


class RelationshipType(str, Enum):
    """Enumerate supported semantic relationships between signal versions."""

    MUTUALLY_EXCLUSIVE = "MUTUALLY_EXCLUSIVE"
    REQUIRES = "REQUIRES"
    IMPLIES = "IMPLIES"
    SUPERSEDES = "SUPERSEDES"
    CORRELATED_WITH = "CORRELATED_WITH"
    SAME_EVENT_AS = "SAME_EVENT_AS"


class RelationshipRequest(ContractModel):
    """Provide two immutable signal versions for relationship inference."""

    source_signal_version_id: str
    target_signal_version_id: str
    source_summary: str
    target_summary: str


class RelationshipProposal(ContractModel):
    """Return an optional inferred relationship with confidence and rationale."""

    relationship: RelationshipType | None
    confidence: Probability
    rationale: str
    metadata: ProviderMetadata


class SimulationSubmission(ContractModel):
    """Submit a reproducible experiment to the authoritative client runtime."""

    experiment_id: str
    idempotency_key: str = Field(min_length=8, max_length=200)
    context_version: str
    state_version: str
    signal_version_ids: list[str]
    disruptions: list[dict[str, Any]]
    scenario_disruptions: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    active_disruptions: list[dict[str, Any]] | None = Field(default=None, max_length=20)
    occurrence_probability: Probability
    provenance: dict[str, Any]


class SimulationAccepted(ContractModel):
    """Acknowledge a client simulation run and its initial status."""

    run_id: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    context_version: str


class SimulationStatus(ContractModel):
    """Report the current lifecycle state of a client simulation run."""

    run_id: str
    status: Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]
    error_code: str | None = None
    error_message: str | None = None
    updated_at: datetime | None = None


class SimulationResults(ContractModel):
    """Return authoritative results and the versions used to produce them."""

    run_id: str
    context_version: str
    state_version: str
    result: dict[str, Any]
    completed_at: datetime


class ExperimentPackage(ContractModel):
    """Immutable, reproducible platform copy of one simulation submission."""

    id: str
    name: str
    context_version: str
    state_version: str
    signal_version_ids: list[str] = Field(min_length=1)
    disruptions: list[dict[str, Any]] = Field(min_length=1)
    occurrence_probability: Probability
    provenance: dict[str, Any]
    validation_summary: dict[str, Any]
    idempotency_key: str
    created_at: datetime
    client_run_id: str | None = None
    status: str


# Planning providers are deliberately separated from authoritative simulation
# contracts.  Everything below is untrusted until a deterministic service has
# validated it through ClientGateway.
class ProposedDisruption(ContractModel):
    """One new hypothetical disruption proposed by the risk provider."""

    type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    classification: Literal[SignalClass.HYPOTHETICAL] = SignalClass.HYPOTHETICAL


class GenerationEntity(ContractModel):
    """Bounded client-grounded entity context exposed to a generation provider."""

    entity_id: str = Field(min_length=1, max_length=200)
    entity_type: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=300)
    attributes: dict[str, Any] = Field(default_factory=dict, max_length=20)


def _validate_generation_scope(scope: list[GenerationEntity]) -> None:
    types: dict[str, str] = {}
    for item in scope:
        previous = types.setdefault(item.entity_id, item.entity_type.casefold())
        if previous != item.entity_type.casefold():
            raise ValueError(f"Entity scope has conflicting types for {item.entity_id}")
    if len(types) != len(scope):
        raise ValueError("Entity scope IDs must be unique")


class RiskSignalCandidate(ContractModel):
    """Bounded stored-signal reference from which the risk provider may select."""

    signal_version_id: str
    classification: Literal[SignalClass.OBSERVED, SignalClass.FORECAST]
    signal_type: str
    temporal_window: TemporalWindow
    occurrence_probability: Probability
    entity_ids: list[str] = Field(default_factory=list, max_length=100)


class RiskGenerationRequest(ContractModel):
    """Bounded, versioned input supplied to exactly one risk provider."""

    context_summary: dict[str, Any]
    context_version: str
    state_version: str
    disruption_contracts: list[DisruptionContract]
    candidate_signals: list[RiskSignalCandidate] = Field(default_factory=list, max_length=20)
    entity_scope: list[GenerationEntity] = Field(default_factory=list, max_length=1000)
    generation_limit: int = Field(default=5, ge=0, le=20)
    fixture_marker: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def unique_entity_scope(self) -> "RiskGenerationRequest":
        _validate_generation_scope(self.entity_scope)
        return self


class RiskScenarioProposal(ContractModel):
    """Untrusted hypothetical scenario proposed by a risk provider."""

    proposal_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    selected_signal_version_ids: list[str] = Field(default_factory=list, max_length=20)
    hypothetical_disruptions: list[ProposedDisruption] = Field(default_factory=list, max_length=20)
    occurrence_probability: Probability
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    rationale: str = Field(min_length=1, max_length=5000)
    metadata: ProviderMetadata

    @model_validator(mode="after")
    def unique_selection(self) -> "RiskScenarioProposal":
        if len(self.selected_signal_version_ids) != len(set(self.selected_signal_version_ids)):
            raise ValueError("Selected signal-version IDs must be unique")
        if not self.selected_signal_version_ids and not self.hypothetical_disruptions:
            raise ValueError("A risk scenario must select or propose at least one disruption")
        return self


class DisruptionApplicationStatus(str, Enum):
    ALREADY_REFLECTED = "ALREADY_REFLECTED"
    APPLY_IN_SIMULATION = "APPLY_IN_SIMULATION"
    UNKNOWN = "UNKNOWN"


class DisruptionReconciliationItem(ContractModel):
    disruption_id: str
    classification: SignalClass
    disruption_type: str
    normalized_payload: dict[str, Any]
    source_signal_version_id: str | None = None


class DisruptionReconciliationRequest(ContractModel):
    context_version: str
    state_version: str
    catalog_version: str
    disruptions: list[DisruptionReconciliationItem] = Field(min_length=1, max_length=20)


class ReconciledDisruption(ContractModel):
    disruption_id: str
    application_status: DisruptionApplicationStatus
    normalized_disruption: dict[str, Any]
    reason_code: str
    classification: SignalClass
    source_signal_version_id: str | None = None


class DisruptionReconciliationResponse(ContractModel):
    context_version: str
    state_version: str
    catalog_version: str
    disruptions: list[ReconciledDisruption] = Field(min_length=1, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=100)


class RiskGenerationResponse(ContractModel):
    """Untrusted result envelope returned by the risk provider."""

    proposals: list[RiskScenarioProposal] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    metadata: ProviderMetadata

    @model_validator(mode="after")
    def unique_proposals(self) -> "RiskGenerationResponse":
        ids = [item.proposal_id for item in self.proposals]
        if len(ids) != len(set(ids)):
            raise ValueError("Risk proposal IDs must be unique")
        return self


class HypothesisGenerationRequest(ContractModel):
    """Ask a provider for browser-reviewable hypothetical risk signals."""

    prompt: str = Field(min_length=1, max_length=5000)
    context_summary: dict[str, Any]
    context_version: str
    disruption_contracts: list[DisruptionContract]
    entity_scope: list[GenerationEntity] = Field(default_factory=list, max_length=1000)
    generation_limit: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def unique_entity_scope(self) -> "HypothesisGenerationRequest":
        _validate_generation_scope(self.entity_scope)
        return self


class HypothesisSignalProposal(ContractModel):
    """One untrusted hypothetical signal retained by the browser until confirmation."""

    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    classification: Literal[SignalClass.HYPOTHETICAL] = SignalClass.HYPOTHETICAL
    signal_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]
    occurrence_probability: Probability
    rationale: str = Field(min_length=1, max_length=5000)
    metadata: ProviderMetadata


class HypothesisGenerationResponse(ContractModel):
    hypotheses: list[HypothesisSignalProposal] = Field(default_factory=list, max_length=10)
    metadata: ProviderMetadata

    @model_validator(mode="after")
    def unique_hypotheses(self) -> "HypothesisGenerationResponse":
        ids = [item.id for item in self.hypotheses]
        if len(ids) != len(set(ids)):
            raise ValueError("Hypothesis IDs must be unique")
        return self


class InterventionContract(ContractModel):
    """One authoritative intervention capability advertised by the client."""

    type: str = Field(min_length=1, max_length=100)
    target_types: list[str]
    payload_schema: dict[str, Any]
    schema_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class InterventionCatalog(ContractModel):
    """Versioned catalog of client-supported interventions."""

    catalog_version: str
    context_version: str
    capability_version: str
    contracts: list[InterventionContract]


class InterventionValidationRequest(ContractModel):
    intervention_type: str
    payload: dict[str, Any]
    catalog_version: str
    context_version: str
    schema_hash: str


class InterventionValidationResponse(ContractModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    normalized_payload: dict[str, Any] | None = None
    catalog_version: str
    context_version: str


class ProposedIntervention(ContractModel):
    """One untrusted planner action; it contains no predicted metrics."""

    type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]


class PlannerRequest(ContractModel):
    """Frozen baseline and capabilities supplied to one planner invocation."""

    planning_cycle_id: str
    scenario_id: str
    context_version: str
    state_version: str
    disruptions: list[dict[str, Any]] = Field(max_length=20)
    baseline_run_id: str
    baseline_results: dict[str, Any]
    intervention_contracts: list[InterventionContract]
    objectives: list[str] = Field(default_factory=list, max_length=50)
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    proposal_limit: int = Field(default=5, ge=0, le=20)
    known_entity_ids: list[str] = Field(default_factory=list, max_length=1000)
    entity_scope: list[GenerationEntity] = Field(default_factory=list, max_length=1000)
    fixture_marker: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def unique_entity_scope(self) -> "PlannerRequest":
        _validate_generation_scope(self.entity_scope)
        return self


class PlanProposal(ContractModel):
    """Untrusted qualitative intervention proposal from the planner."""

    proposal_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    interventions: list[ProposedIntervention] = Field(min_length=1, max_length=20)
    rationale: str = Field(min_length=1, max_length=5000)
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    expected_qualitative_effects: list[str] = Field(default_factory=list, max_length=50)
    metadata: ProviderMetadata


class PlannerResponse(ContractModel):
    proposals: list[PlanProposal] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    metadata: ProviderMetadata

    @model_validator(mode="after")
    def unique_proposals(self) -> "PlannerResponse":
        ids = [item.proposal_id for item in self.proposals]
        if len(ids) != len(set(ids)):
            raise ValueError("Plan proposal IDs must be unique")
        return self
