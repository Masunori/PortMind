"""HTTP-only client gateway boundary."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Protocol, TypeVar
from uuid import uuid4

import httpx
from pydantic import BaseModel, ValidationError

from app.integrations.contracts import (
    ContextManifest, DisruptionCatalog, DisruptionContract,
    DisruptionValidationRequest, DisruptionValidationResponse, EntityCandidate,
    EntityResolution, EntityResolveRequest, EntitySearchRequest, EntitySearchResponse,
    EntityResolutionCapabilities, EntityStatus, ModelSchemaResponse, SimulationAccepted, SimulationResults,
    SimulationStatus, SimulationSubmission, StateQueryRequest, StateQueryResponse,
    InterventionCatalog, InterventionContract, InterventionValidationRequest,
    InterventionValidationResponse,
    DisruptionReconciliationRequest, DisruptionReconciliationResponse,
    ReconciledDisruption,
)
from app.integrations.errors import (
    ClientAuthenticationError, ClientContractError, ClientGatewayError,
    ClientRateLimitError, ClientTimeoutError, ClientUnavailableError,
    StaleClientContextError,
    ClientIdempotencyConflictError, ClientConflictError,
)

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


def _conflict_detail(value: Any, secrets: list[str], depth: int = 0) -> Any:
    """Keep bounded diagnostic fields, excluding arbitrary payloads and credentials."""
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        allowed = {"detail", "error", "errors", "code", "message", "reason",
                   "context_version", "state_version", "catalog_version",
                   "expected", "actual", "received", "current"}
        return {key: _conflict_detail(item, secrets, depth + 1)
                for key, item in value.items() if key in allowed or key in {
                    f"{prefix}_{version}_version" for prefix in ("expected", "actual", "received", "current")
                    for version in ("context", "state", "catalog")}}
    if isinstance(value, list):
        return [_conflict_detail(item, secrets, depth + 1) for item in value[:10]]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[redacted]")
        return value[:1000]
    return value if value is None or isinstance(value, (int, float, bool)) else "[omitted]"


class ClientGateway(Protocol):
    """Define all authoritative operations supplied by a connected client."""

    async def get_context(self) -> ContextManifest: ...
    async def get_schema(self) -> ModelSchemaResponse: ...
    async def search_entities(self, request: EntitySearchRequest) -> EntitySearchResponse: ...
    async def get_entity_resolution_capabilities(self) -> EntityResolutionCapabilities: ...
    async def resolve_entity(self, request: EntityResolveRequest) -> EntityResolution: ...
    async def query_state(self, request: StateQueryRequest) -> StateQueryResponse: ...
    async def get_disruption_contracts(self) -> DisruptionCatalog: ...
    async def validate_disruption(self, request: DisruptionValidationRequest) -> DisruptionValidationResponse: ...
    async def reconcile_disruptions(self, request: DisruptionReconciliationRequest) -> DisruptionReconciliationResponse: ...
    async def get_intervention_contracts(self) -> InterventionCatalog: ...
    async def validate_intervention(self, request: InterventionValidationRequest) -> InterventionValidationResponse: ...
    async def submit_simulation(self, request: SimulationSubmission) -> SimulationAccepted: ...
    async def get_simulation(self, run_id: str) -> SimulationStatus: ...
    async def get_simulation_results(self, run_id: str, *, context_version: str | None = None,
                                     state_version: str | None = None,
                                     completed_at: datetime | None = None) -> SimulationResults: ...


def _canonical_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class HTTPClientGateway:
    """Bounded adapter for the separately deployed authoritative client."""

    def __init__(self, base_url: str, *, token: str | None = None, timeout_seconds: float = 10,
                 max_retries: int = 2, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._client = client
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def _request_json(self, method: str, path: str,
                            body: BaseModel | dict[str, Any] | None = None,
                            *, idempotency_key: str | None = None) -> Any:
        headers = {**self._headers, "X-Correlation-ID": str(uuid4())}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)
        try:
            for attempt in range(self._max_retries + 1):
                try:
                    payload = body.model_dump(mode="json") if isinstance(body, BaseModel) else body
                    response = await client.request(method, path, json=payload, headers=headers)
                except httpx.TimeoutException as error:
                    if attempt == self._max_retries:
                        raise ClientTimeoutError("Client request timed out", retryable=True) from error
                    await asyncio.sleep(0)
                    continue
                except httpx.HTTPError as error:
                    raise ClientUnavailableError("Client is unavailable", retryable=True) from error
                if response.status_code in (401, 403):
                    raise ClientAuthenticationError("Client authentication failed")
                if response.status_code == 409:
                    try:
                        detail = response.json()
                    except ValueError:
                        detail = {"message": "Non-JSON conflict response"}
                    authorization = self._headers.get("Authorization", "")
                    secrets = [value for value in (authorization, authorization.removeprefix("Bearer ")) if value]
                    versions = {key: value for key, value in (payload or {}).items()
                                if key in {"context_version", "state_version", "catalog_version",
                                           "schema_version", "capability_version"}}
                    logger.warning("Client gateway conflict: %s", json.dumps({
                        "method": method, "path": path, "status": 409,
                        "correlation_id": headers["X-Correlation-ID"],
                        "submitted_versions": _conflict_detail(versions, secrets),
                        "response_detail": _conflict_detail(detail, secrets),
                    }, default=str))
                    error_detail = detail
                    for _ in range(4):
                        if not isinstance(error_detail, dict) or "code" in error_detail:
                            break
                        error_detail = error_detail.get("error", error_detail.get("detail"))
                    code = error_detail.get("code") if isinstance(error_detail, dict) else None
                    if code == "IDEMPOTENCY_CONFLICT":
                        raise ClientIdempotencyConflictError(
                            "Simulation request key was already used for a different request")
                    if code in {"STALE_CONTEXT", "STALE_STATE", "STALE_CATALOG"}:
                        raise StaleClientContextError("Client context or state is stale")
                    raise ClientConflictError("Client rejected the request with a conflict")
                if response.status_code == 429:
                    raise ClientRateLimitError("Client rate limit exceeded", retryable=True)
                if response.status_code >= 500 and attempt < self._max_retries:
                    await asyncio.sleep(0)
                    continue
                if response.is_error:
                    raise ClientGatewayError(
                        f"Client rejected {method} {path} with status {response.status_code}")
                try:
                    return response.json()
                except ValueError as error:
                    raise ClientContractError("Client returned malformed JSON") from error
            raise ClientUnavailableError("Client is unavailable", retryable=True)
        finally:
            if owns_client:
                await client.aclose()

    async def get_context(self) -> ContextManifest:
        raw = await self._request_json("GET", "/context")
        try:
            return ContextManifest(client_id=raw["model_id"], compact_context={}, **{
                key: raw[key] for key in ("context_version", "schema_version", "state_version",
                                          "capability_version", "generated_at")})
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned a malformed context response") from error

    async def get_schema(self) -> ModelSchemaResponse:
        raw, context = await asyncio.gather(self._request_json("GET", "/schema"), self.get_context())
        try:
            return ModelSchemaResponse(schema_version=raw["schema_version"],
                context_version=context.context_version, schema_document=raw)
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned a malformed schema response") from error

    async def search_entities(self, request: EntitySearchRequest) -> EntitySearchResponse:
        raw = await self._request_json("POST", "/entities/search", request)
        try:
            candidates = [EntityCandidate(entity_id=item["id"], entity_type=item["entity_type"],
                display_name=item["name"], confidence=1) for item in raw["results"]]
            return EntitySearchResponse(candidates=candidates, context_version=request.context_version)
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed entity search results") from error

    async def get_entity_resolution_capabilities(self) -> EntityResolutionCapabilities:
        raw = await self._request_json("GET", "/entity-resolution/capabilities")
        try:
            if not isinstance(raw, dict) or not isinstance(raw.get("entity_types"), dict):
                raise TypeError("entity_types must be an object")
            return EntityResolutionCapabilities(
                contract_version=raw["contract_version"],
                entity_registry_version=raw["entity_registry_version"],
                manifest=raw,
            )
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError(
                "Client returned malformed entity-resolution capabilities"
            ) from error

    async def resolve_entity(self, request: EntityResolveRequest) -> EntityResolution:
        raw = await self._request_json("POST", "/entities/resolve", {
            "mentions": [{"value": request.mention, "entity_type": request.entity_type}],
            "context_version": request.context_version})
        try:
            result = raw["results"][0]
            candidates = [EntityCandidate(entity_id=item["id"], entity_type=item["entity_type"],
                display_name=item["name"], confidence=1) for item in result.get("candidates", [])]
            if request.candidate_id:
                candidates = [item for item in candidates if item.entity_id == request.candidate_id]
            status = EntityStatus(result["status"])
            entity = candidates[0] if status == EntityStatus.RESOLVED and len(candidates) == 1 else None
            return EntityResolution(status=status, context_version=request.context_version,
                entity=entity, candidates=[] if entity else candidates, method="client-authoritative",
                confidence=1 if entity else 0)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise ClientContractError("Client returned malformed entity resolution results") from error

    async def query_state(self, request: StateQueryRequest) -> StateQueryResponse:
        raw = await self._request_json("POST", "/state/query", request)
        try:
            return StateQueryResponse(context_version=request.context_version,
                state_version=raw["state_version"], records=raw["results"])
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed state results") from error

    async def get_disruption_contracts(self) -> DisruptionCatalog:
        raw, context = await asyncio.gather(
            self._request_json("GET", "/disruption-contracts"), self.get_context())
        try:
            contracts = [DisruptionContract(type=item["type"], target_types=item["valid_target_types"],
                payload_schema=item["payload_schema"], schema_hash=_canonical_hash(item["payload_schema"]))
                for item in raw["disruption_types"]]
            return DisruptionCatalog(catalog_version=raw["catalog_version"],
                context_version=context.context_version, capability_version=context.capability_version,
                contracts=contracts)
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed disruption contracts") from error

    async def validate_disruption(self, request: DisruptionValidationRequest) -> DisruptionValidationResponse:
        raw = await self._request_json("POST", "/disruptions/validate", {
            "context_version": request.context_version,
            "catalog_version": request.catalog_version,
            "disruption": {"type": request.disruption_type, "payload": request.payload}})
        try:
            return DisruptionValidationResponse(valid=raw["valid"], errors=raw.get("errors", []),
                normalized_payload=raw.get("normalized_disruption"),
                catalog_version=request.catalog_version, context_version=request.context_version)
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed disruption validation") from error

    async def reconcile_disruptions(
        self, request: DisruptionReconciliationRequest,
    ) -> DisruptionReconciliationResponse:
        raw = await self._request_json("POST", "/disruptions/reconcile", request)
        try:
            return DisruptionReconciliationResponse(
                context_version=raw["context_version"], state_version=raw["state_version"],
                catalog_version=raw["catalog_version"], warnings=raw.get("warnings", []),
                disruptions=[ReconciledDisruption.model_validate(item)
                             for item in raw["disruptions"]])
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed disruption reconciliation") from error

    async def get_intervention_contracts(self) -> InterventionCatalog:
        raw, context = await asyncio.gather(
            self._request_json("GET", "/intervention-contracts"), self.get_context())
        try:
            contracts = [InterventionContract(type=item["type"], target_types=item["valid_target_types"],
                payload_schema=item["payload_schema"], schema_hash=_canonical_hash(item["payload_schema"]))
                for item in raw["intervention_types"]]
            return InterventionCatalog(catalog_version=raw["catalog_version"],
                context_version=context.context_version, capability_version=context.capability_version,
                contracts=contracts)
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed intervention contracts") from error

    async def validate_intervention(self, request: InterventionValidationRequest) -> InterventionValidationResponse:
        raw = await self._request_json("POST", "/interventions/validate", {
            "context_version": request.context_version,
            "catalog_version": request.catalog_version,
            "intervention": {"type": request.intervention_type, "payload": request.payload}})
        try:
            return InterventionValidationResponse(valid=raw["valid"], errors=raw.get("errors", []),
                normalized_payload=raw.get("normalized_intervention"),
                catalog_version=request.catalog_version, context_version=request.context_version)
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed intervention validation") from error

    async def submit_simulation(self, request: SimulationSubmission) -> SimulationAccepted:
        scenario_disruptions = []
        for item in request.scenario_disruptions:
            try:
                normalized = item.get("normalized_disruption") or {
                    "type": item["type"], "payload": item["payload"]}
                scenario_disruptions.append({
                    "disruption_id": item["disruption_id"],
                    "classification": item["classification"],
                    "source_signal_version_id": item.get("source_signal_version_id"),
                    "application_status": item["application_status"],
                    "normalized_disruption": normalized,
                    "reason_code": item["reason_code"],
                })
            except (KeyError, TypeError) as error:
                raise ClientContractError(
                    "Scenario disruption is missing reconciliation metadata") from error
        body = {"context_version": request.context_version, "state_version": request.state_version,
                "disruptions": request.active_disruptions if request.active_disruptions is not None else request.disruptions,
                "scenario_disruptions": scenario_disruptions,
                "interventions": request.provenance.get("interventions", []),
                "experiment_id": request.experiment_id,
                "provenance": request.provenance}
        # Bind retries to both the logical operation and the complete wire payload.
        # Provenance and experiment IDs can differ even when scenarios are identical.
        wire_key = _canonical_hash({"version": "simulation-v2",
            "operation_key": request.idempotency_key, "body": body})
        body["idempotency_key"] = wire_key
        raw = await self._request_json("POST", "/simulations", body,
                                       idempotency_key=wire_key)
        try:
            return SimulationAccepted(run_id=raw["id"], status=raw["status"],
                                      context_version=request.context_version)
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed simulation acceptance") from error

    async def get_simulation(self, run_id: str) -> SimulationStatus:
        raw = await self._request_json("GET", f"/simulations/{run_id}")
        try:
            error = raw.get("error") or {}
            return SimulationStatus(run_id=raw["id"], status=raw["status"],
                error_code=error.get("code"), error_message=error.get("message"),
                updated_at=raw.get("updated_at"))
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed simulation status") from error

    async def get_simulation_results(self, run_id: str, *, context_version: str | None = None,
                                     state_version: str | None = None,
                                     completed_at: datetime | None = None) -> SimulationResults:
        raw = await self._request_json("GET", f"/simulations/{run_id}/results")
        try:
            if raw["status"] != "COMPLETED":
                raise ClientGatewayError("Simulation results are not ready", retryable=True)
            if not context_version or not state_version:
                raise ClientContractError("Result retrieval requires experiment versions")
            return SimulationResults(run_id=raw["id"], context_version=context_version,
                state_version=state_version, result=raw["results"],
                completed_at=completed_at or datetime.now(timezone.utc))
        except ClientGatewayError:
            raise
        except (KeyError, TypeError, ValidationError) as error:
            raise ClientContractError("Client returned malformed simulation results") from error
