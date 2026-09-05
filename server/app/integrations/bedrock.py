"""Amazon Bedrock Converse adapters for purpose-specific provider protocols."""

import asyncio
import json
from typing import Any, Callable, TypeVar

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectionClosedError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from pydantic import BaseModel, ValidationError

from app.integrations.contracts import ProviderMetadata
from app.integrations.model_provider import (
    FilterProviderBehavior, HypothesisProviderBehavior, InterpreterProviderBehavior,
    PlannerProviderBehavior, RiskProviderBehavior,
)


OutputModel = TypeVar("OutputModel", bound=BaseModel)


_UNSUPPORTED_OUTPUT_SCHEMA_KEYS = frozenset({
    "default",
    "maximum",
    "maxItems",
    "maxLength",
    "minimum",
    "multipleOf",
    "minLength",
})


def _bedrock_output_schema(output_type: type[OutputModel]) -> dict[str, Any]:
    """Remove constraints unsupported by Bedrock's structured-output subset.

    The original Pydantic model remains authoritative and validates the response
    after generation, so removing provider-side constraints does not weaken the
    application boundary.
    """

    def normalize(value: Any) -> Any:
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value
        return {
            key: normalize(item)
            for key, item in value.items()
            if key not in _UNSUPPORTED_OUTPUT_SCHEMA_KEYS
            and not (key == "additionalProperties" and item is True)
        }

    return normalize(output_type.model_json_schema())

class BedrockSchemaError(ValueError):
    """Raised when Bedrock exhausts correction attempts for a provider contract."""


class BedrockAPIError(RuntimeError):
    """Sanitized terminal Bedrock failure safe for API responses and logs."""

    def __init__(self, message: str, *, status_code: int, retryable: bool) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class BedrockRateLimitError(BedrockAPIError):
    """Bedrock quota or request-rate exhaustion after SDK retries."""


class _BedrockStructuredProvider:
    """Call Converse structured output without blocking the async event loop."""

    _retryable_codes = {
        "InternalServerException",
        "ModelNotReadyException",
        "ModelTimeoutException",
        "ServiceQuotaExceededException",
        "ServiceUnavailableException",
        "ThrottlingException",
    }
    _rate_limit_codes = {"ServiceQuotaExceededException", "ThrottlingException"}

    def __init__(self, *, model: str, region: str | None = None,
                 max_attempts: int = 3, timeout_seconds: float = 60,
                 max_tokens: int = 4096, sdk_max_attempts: int = 2,
                 client: Any | None = None,
                 system_prompt: str | None = None) -> None:
        if not model.strip():
            raise ValueError("BEDROCK_MODEL_ID is required for Bedrock providers")
        if max_attempts < 1:
            raise ValueError("Bedrock max_attempts must be at least 1")
        if max_tokens < 1:
            raise ValueError("Bedrock max_tokens must be at least 1")
        if timeout_seconds <= 0:
            raise ValueError("Bedrock timeout_seconds must be greater than 0")
        if sdk_max_attempts < 1:
            raise ValueError("Bedrock sdk_max_attempts must be at least 1")
        self._model = model.strip()
        self._region = region or None
        self._max_attempts = max_attempts
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
        self._sdk_max_attempts = sdk_max_attempts
        self._client = client
        self._system_prompt = system_prompt

    def _runtime_client(self):
        if self._client is None:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=self._region,
                config=Config(
                    connect_timeout=self._timeout,
                    read_timeout=self._timeout,
                    # Transport retries are deliberately independent from schema
                    # correction attempts so their worst-case product is explicit.
                    retries={"mode": "standard", "total_max_attempts": self._sdk_max_attempts},
                ),
            )
        return self._client

    async def _generate(
        self, prompt: str, output_type: type[OutputModel],
        validate: Callable[[OutputModel], None] | None = None,
    ) -> tuple[OutputModel, str | None]:
        validation_error = ""
        schema = _bedrock_output_schema(output_type)
        schema_name = output_type.__name__.removeprefix("_").lower()
        uses_tool_output = "amazon.nova-2-" in self._model
        for attempt in range(1, self._max_attempts + 1):
            attempt_prompt = prompt
            if validation_error:
                attempt_prompt += (
                    "\n\nYour previous response failed local schema validation. Return a corrected "
                    f"object. Validation errors:\n{validation_error}"
                )
            request: dict[str, Any] = {
                "modelId": self._model,
                "messages": [{"role": "user", "content": [{"text": attempt_prompt}]}],
                "inferenceConfig": {"temperature": 0, "maxTokens": self._max_tokens},
            }
            if uses_tool_output:
                request["toolConfig"] = {
                    "tools": [{"toolSpec": {
                        "name": schema_name,
                        "description": "Return the validated AEGIS provider response",
                        "inputSchema": {"json": schema},
                    }}],
                    "toolChoice": {"tool": {"name": schema_name}},
                }
            else:
                request["outputConfig"] = {
                    "textFormat": {
                        "type": "json_schema",
                        "structure": {
                            "jsonSchema": {
                                "schema": json.dumps(schema),
                                "name": schema_name,
                                "description": "Validated AEGIS provider response",
                            }
                        },
                    }
                }
            if self._system_prompt:
                request["system"] = [{"text": self._system_prompt}]
            response = await self._converse(request)
            try:
                blocks = response["output"]["message"]["content"]
                if uses_tool_output:
                    raw_output = next(
                        block["toolUse"]["input"] for block in blocks
                        if block.get("toolUse", {}).get("name") == schema_name
                    )
                else:
                    raw_text = next(block["text"] for block in blocks if "text" in block)
                    raw_output = json.loads(raw_text)
                output = output_type.model_validate(raw_output)
                if validate is not None:
                    validate(output)
                request_id = response.get("ResponseMetadata", {}).get("RequestId")
                return output, request_id
            except (KeyError, StopIteration, TypeError, ValueError,
                    json.JSONDecodeError, ValidationError) as error:
                validation_error = str(error)
                if attempt == self._max_attempts:
                    raise BedrockSchemaError(
                        f"Bedrock returned invalid structured output after {attempt} attempts"
                    ) from error
        raise AssertionError("unreachable")

    async def _converse(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            # Injected clients are test doubles; production boto3 calls run off-loop.
            if self._client is not None:
                return self._client.converse(**request)
            return await asyncio.to_thread(self._runtime_client().converse, **request)
        except ClientError as error:
            details = error.response.get("Error", {})
            code = str(details.get("Code", "ClientError"))
            status = int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 502))
            retryable = code in self._retryable_codes or status >= 500
            error_type = BedrockRateLimitError if code in self._rate_limit_codes else BedrockAPIError
            if error_type is BedrockRateLimitError:
                status = 429
            prefix = ("Bedrock rate limit or quota exhausted"
                      if error_type is BedrockRateLimitError else f"Bedrock request failed ({code})")
            # Provider messages are not reflected because they may contain request
            # fragments or account-specific details. The stable code is sufficient.
            raise error_type(prefix,
                             status_code=status, retryable=retryable) from error
        except (ConnectionClosedError, EndpointConnectionError, ReadTimeoutError) as error:
            raise BedrockAPIError("Bedrock is temporarily unreachable",
                                  status_code=503, retryable=True) from error
        except BotoCoreError as error:
            raise BedrockAPIError("Bedrock SDK request failed",
                                  status_code=502, retryable=False) from error

    def _metadata(self, component: str, request_id: str | None, *,
                  prompt_version: str | None = None) -> ProviderMetadata:
        return ProviderMetadata(provider="bedrock", model=self._model,
            prompt_version=prompt_version or f"{component}-v1",
            request_id=request_id, stub=False)


class BedrockFilterProvider(_BedrockStructuredProvider, FilterProviderBehavior):
    """Classify canonical evidence through Bedrock Converse."""


class BedrockInterpreterProvider(_BedrockStructuredProvider, InterpreterProviderBehavior):
    """Extract ungrounded signal proposals through Bedrock Converse."""


class BedrockRiskProvider(_BedrockStructuredProvider, RiskProviderBehavior):
    """Generate bounded risk scenarios through Bedrock Converse."""


class BedrockPlannerProvider(_BedrockStructuredProvider, PlannerProviderBehavior):
    """Generate bounded intervention plans through Bedrock Converse."""


class BedrockHypothesisProvider(_BedrockStructuredProvider, HypothesisProviderBehavior):
    """Generate review-only hypothetical signals through Bedrock Converse."""


class BedrockPlannerPanelProvider:
    """Run a bounded role-specialized panel of Bedrock planners concurrently."""

    roles = (
        ("continuity", "Prioritize operational continuity and service recovery."),
        ("cost", "Prioritize resource efficiency and cost control."),
        ("resilience", "Prioritize robust mitigation under uncertainty."),
        ("responsiveness", "Prioritize speed of implementation and near-term risk reduction."),
        ("sustainability", "Prioritize durable and environmentally responsible mitigation."),
    )

    def __init__(self, *, model: str, region: str | None = None,
                 max_attempts: int = 3, timeout_seconds: float = 60,
                 max_tokens: int = 4096, sdk_max_attempts: int = 2,
                 client: Any | None = None,
                 agent_prompts: list[str] | None = None,
                 agent_count: int = 3) -> None:
        if not 1 <= agent_count <= 5:
            raise ValueError("Panel agent count must be between 1 and 5")
        if agent_prompts is not None and len(agent_prompts) < agent_count:
            raise ValueError("A system prompt is required for every panel agent")
        self._model = model
        self._planners = [
            (role, BedrockPlannerProvider(model=model, region=region,
                max_attempts=max_attempts, timeout_seconds=timeout_seconds,
                max_tokens=max_tokens, sdk_max_attempts=sdk_max_attempts, client=client,
                system_prompt=((agent_prompts[index] + "\n\n") if agent_prompts else "")
                + f"Panel role: {role}. {directive} Produce exactly one distinct proposal."))
            for index, (role, directive) in enumerate(self.roles[:agent_count])
        ]

    async def propose_plans(self, request):
        active = self._planners[:request.proposal_limit]
        metadata = ProviderMetadata(provider="bedrock-panel", model=self._model,
            prompt_version="panel-v1", stub=False)
        if not active:
            from app.integrations.contracts import PlannerResponse
            return PlannerResponse(metadata=metadata)
        role_request = request.model_copy(update={"proposal_limit": 1})
        results = await asyncio.gather(*(
            planner.propose_plans(role_request) for _, planner in active),
            return_exceptions=True)
        proposals = []
        warnings = []
        for (role, _), result in zip(active, results):
            if isinstance(result, Exception):
                warnings.append(f"{role}: provider unavailable")
                continue
            warnings.extend(f"{role}: {warning}" for warning in result.warnings)
            for proposal in result.proposals[:1]:
                role_metadata = proposal.metadata.model_copy(update={
                    "provider": "bedrock-panel", "prompt_version": f"panel-{role}-v1"})
                proposals.append(proposal.model_copy(update={
                    "proposal_id": f"{role}-{proposal.proposal_id}"[:120],
                    "metadata": role_metadata,
                }))
        from app.integrations.contracts import PlannerResponse
        return PlannerResponse(proposals=proposals, warnings=warnings[:100], metadata=metadata)
