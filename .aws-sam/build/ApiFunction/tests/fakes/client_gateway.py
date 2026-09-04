"""Deterministic, configurable fake for the client gateway contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.contracts import (
    ContextManifest, DisruptionCatalog, DisruptionContract, DisruptionValidationRequest,
    DisruptionValidationResponse, EntityResolution, EntityResolveRequest,
    EntityCandidate, EntitySearchRequest, EntitySearchResponse, EntityStatus, ModelSchemaResponse,
    EntityResolutionCapabilities,
    SimulationAccepted, SimulationResults, SimulationStatus,
    SimulationSubmission, StateQueryRequest, StateQueryResponse,
    InterventionCatalog, InterventionContract, InterventionValidationRequest,
    InterventionValidationResponse,
    DisruptionApplicationStatus, DisruptionReconciliationRequest,
    DisruptionReconciliationResponse, ReconciledDisruption,
)
from app.integrations.schema_validation import schema_hash


class FakeClientGateway:
    """Return injected contract objects and record every request.

    A method name placed in ``failures`` raises that exception deterministically.
    This fake intentionally contains no database or local operational-model access.
    """

    def __init__(self, **responses: Any) -> None:
        self.context = responses.get("context") or ContextManifest(
            client_id="fake-client", context_version="context-v1",
            schema_version="schema-v1", capability_version="capability-v1",
            state_version="state-v1", generated_at=datetime.now(timezone.utc),
            compact_context={},
        )
        self.responses = responses
        self.entities: list[EntityCandidate] = responses.get("entities", [])
        self.failures: dict[str, Exception] = {}
        self.calls: list[tuple[str, Any]] = []
        self._runs: dict[str, SimulationStatus] = {}

    def fail(self, method: str, error: Exception) -> None:
        self.failures[method] = error

    def _record(self, method: str, request: Any = None) -> None:
        self.calls.append((method, request))
        if method in self.failures:
            raise self.failures[method]

    async def get_context(self) -> ContextManifest:
        self._record("get_context")
        return self.context

    async def get_schema(self) -> ModelSchemaResponse:
        self._record("get_schema")
        return self.responses.get("schema") or ModelSchemaResponse(
            schema_version=self.context.schema_version,
            context_version=self.context.context_version, schema_document={},
        )

    async def search_entities(self, request: EntitySearchRequest) -> EntitySearchResponse:
        self._record("search_entities", request)
        candidates = [item for item in self.entities
                      if request.query.casefold() in item.display_name.casefold()]
        return self.responses.get("search") or EntitySearchResponse(
            candidates=candidates[:request.limit], context_version=request.context_version)

    async def get_entity_resolution_capabilities(self) -> EntityResolutionCapabilities:
        self._record("get_entity_resolution_capabilities")
        return self.responses.get("entity_resolution_capabilities") or EntityResolutionCapabilities(
            contract_version="entity-resolution-v1",
            entity_registry_version="fake-registry-v1",
            manifest={
                "contract_version": "entity-resolution-v1",
                "entity_registry_version": "fake-registry-v1",
                "entity_types": {"PORT": {"optional_hints": ["name", "unlocode"]}},
            },
        )

    async def resolve_entity(self, request: EntityResolveRequest) -> EntityResolution:
        self._record("resolve_entity", request)
        response = self.responses.get("resolution")
        if response is not None:
            return response
        matches = [item for item in self.entities
                   if item.display_name.casefold() == request.mention.casefold()]
        if len(matches) == 1:
            return EntityResolution(status=EntityStatus.RESOLVED,
                context_version=request.context_version, entity=matches[0],
                method="fake-exact-name", confidence=matches[0].confidence)
        return EntityResolution(status=EntityStatus.NOT_FOUND,
            context_version=request.context_version, method="fake-exact-name", confidence=0)

    async def query_state(self, request: StateQueryRequest) -> StateQueryResponse:
        self._record("query_state", request)
        return self.responses.get("state") or StateQueryResponse(
            context_version=request.context_version,
            state_version=self.context.state_version, records=[])

    async def get_disruption_contracts(self) -> DisruptionCatalog:
        self._record("get_disruption_contracts")
        response = self.responses.get("catalog")
        if response is not None:
            return response
        schema = {
            "type": "object", "additionalProperties": False,
            "required": ["target_ids", "effective_from", "effective_until", "parameters"],
            "properties": {
                "target_ids": {"type": "array", "items": {"type": "string", "maxLength": 100}, "maxItems": 100},
                "effective_from": {"type": "string", "format": "date-time"},
                "effective_until": {"type": ["string", "null"], "format": "date-time"},
                "parameters": {"type": "object", "additionalProperties": False,
                    "required": ["capacity_multiplier"],
                    "properties": {"capacity_multiplier": {"type": "number", "minimum": 0, "maximum": 1}}},
            },
        }
        return DisruptionCatalog(catalog_version="catalog-v1",
            context_version=self.context.context_version,
            capability_version=self.context.capability_version,
            contracts=[DisruptionContract(type="PORT_CAPACITY_CHANGE", target_types=["PORT"],
                payload_schema=schema, schema_hash=schema_hash(schema))])

    async def validate_disruption(
        self, request: DisruptionValidationRequest,
    ) -> DisruptionValidationResponse:
        self._record("validate_disruption", request)
        return self.responses.get("validation") or DisruptionValidationResponse(
            valid=True, normalized_payload={"type": request.disruption_type, "payload": request.payload},
            catalog_version=request.catalog_version,
            context_version=request.context_version)

    async def reconcile_disruptions(
        self, request: DisruptionReconciliationRequest,
    ) -> DisruptionReconciliationResponse:
        self._record("reconcile_disruptions", request)
        response = self.responses.get("reconciliation")
        if response is not None: return response
        return DisruptionReconciliationResponse(context_version=request.context_version,
            state_version=request.state_version, catalog_version=request.catalog_version,
            disruptions=[ReconciledDisruption(disruption_id=item.disruption_id,
                application_status=DisruptionApplicationStatus.APPLY_IN_SIMULATION,
                normalized_disruption={"type": item.disruption_type, "payload": item.normalized_payload},
                reason_code="NOT_REFLECTED", classification=item.classification,
                source_signal_version_id=item.source_signal_version_id)
                for item in request.disruptions])

    async def get_intervention_contracts(self) -> InterventionCatalog:
        self._record("get_intervention_contracts")
        response = self.responses.get("intervention_catalog")
        if response is not None: return response
        schema = {"type": "object", "additionalProperties": False,
                  "required": ["target_ids"], "properties": {"target_ids": {
                      "type": "array", "items": {"type": "string"}, "maxItems": 100}}}
        return InterventionCatalog(catalog_version="interventions-v1",
            context_version=self.context.context_version,
            capability_version=self.context.capability_version,
            contracts=[InterventionContract(type="EXPEDITE", target_types=["SHIPMENT"],
                payload_schema=schema, schema_hash=schema_hash(schema))])

    async def validate_intervention(self, request: InterventionValidationRequest) -> InterventionValidationResponse:
        self._record("validate_intervention", request)
        return self.responses.get("intervention_validation") or InterventionValidationResponse(
            valid=True, normalized_payload={"type": request.intervention_type, "payload": request.payload},
            catalog_version=request.catalog_version, context_version=request.context_version)

    async def submit_simulation(self, request: SimulationSubmission) -> SimulationAccepted:
        self._record("submit_simulation", request)
        accepted = self.responses.get("accepted") or SimulationAccepted(
            run_id="fake-run-1", status="COMPLETED",
            context_version=request.context_version)
        self._runs[accepted.run_id] = SimulationStatus(
            run_id=accepted.run_id, status=accepted.status)
        return accepted

    async def get_simulation(self, run_id: str) -> SimulationStatus:
        self._record("get_simulation", run_id)
        return self.responses.get("status") or self._runs[run_id]

    async def get_simulation_results(self, run_id: str, **_versions: Any) -> SimulationResults:
        self._record("get_simulation_results", run_id)
        return self.responses.get("results") or SimulationResults(
            run_id=run_id, context_version=self.context.context_version,
            state_version=self.context.state_version, result={},
            completed_at=datetime.now(timezone.utc))
