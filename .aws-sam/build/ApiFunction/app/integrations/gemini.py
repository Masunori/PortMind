"""Gemini structured-output adapters for purpose-specific provider protocols."""

import asyncio
from copy import deepcopy
import json
from typing import Any, Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.integrations.contracts import (
    PlanProposal, PlannerRequest, PlannerResponse, ProviderMetadata,
)
from app.integrations.model_provider import (
    FilterOutput, FilterProviderBehavior, HypothesisOutput,
    HypothesisProviderBehavior, InterpreterOutput, InterpreterProviderBehavior,
    PlannerOutput, PlannerProviderBehavior, RiskOutput, RiskProviderBehavior,
    json_object,
)

OutputModel = TypeVar("OutputModel", bound=BaseModel)


class GeminiSchemaError(ValueError):
    """Raised when Gemini exhausts its attempts without returning a valid contract."""


class GeminiAPIError(RuntimeError):
    """Sanitized terminal Gemini API failure safe for operational reporting."""

    def __init__(self, message: str, *, status_code: int, retryable: bool) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class GeminiRateLimitError(GeminiAPIError):
    """Gemini quota or request-rate exhaustion after bounded retries."""


# Compatibility aliases retained for existing imports and schema tests.
_GeminiFilterOutput = FilterOutput
_GeminiInterpreterOutput = InterpreterOutput
_GeminiHypothesisOutput = HypothesisOutput
_GeminiRiskOutput = RiskOutput
_GeminiPlannerOutput = PlannerOutput


class _GeminiStructuredProvider:
    """Call Gemini structured output and validate each response with Pydantic."""

    def __init__(self, *, api_key: str, model: str = "gemini-flash-lite-latest",
                 max_attempts: int = 3, timeout_seconds: float = 30,
                 client: httpx.AsyncClient | None = None,
                 system_prompt: str | None = None) -> None:
        if not api_key.strip():
            raise ValueError("GEMINI_API_KEY is required for Gemini providers")
        if max_attempts < 1:
            raise ValueError("Gemini max_attempts must be at least 1")
        self._api_key = api_key
        self._model = model
        self._max_attempts = max_attempts
        self._timeout = timeout_seconds
        self._client = client
        self._system_prompt = system_prompt

    async def _generate(
        self, prompt: str, output_type: type[OutputModel],
        validate: Callable[[OutputModel], None] | None = None,
    ) -> tuple[OutputModel, str | None]:
        validation_error = ""
        for attempt in range(1, self._max_attempts + 1):
            attempt_prompt = prompt
            if validation_error:
                attempt_prompt += (
                    "\n\nYour previous response failed local schema validation. Return a corrected "
                    f"object. Validation errors:\n{validation_error}"
                )
            payload: dict[str, Any] = {
                "contents": [{"parts": [{"text": attempt_prompt}]}],
                "generationConfig": {
                    "temperature": 0,
                    "responseMimeType": "application/json",
                    "responseJsonSchema": _gemini_schema(output_type),
                },
            }
            if self._system_prompt:
                payload["systemInstruction"] = {
                    "parts": [{"text": self._system_prompt}],
                }
            response = await self._post_with_retry(payload)
            try:
                raw_text = response["candidates"][0]["content"]["parts"][0]["text"]
                output = output_type.model_validate(json.loads(raw_text))
                if validate is not None:
                    validate(output)
                return output, response.get("responseId")
            except (KeyError, IndexError, TypeError, ValueError,
                    json.JSONDecodeError, ValidationError) as error:
                validation_error = str(error)
                if attempt == self._max_attempts:
                    raise GeminiSchemaError(
                        f"Gemini returned invalid structured output after {attempt} attempts"
                    ) from error
        raise AssertionError("unreachable")

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self._model}:generateContent")
        if self._client is not None:
            response = await self._client.post(
                url, headers={"x-goog-api-key": self._api_key}, json=payload,
                timeout=self._timeout)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url, headers={"x-goog-api-key": self._api_key}, json=payload)
        response.raise_for_status()
        return response.json()

    async def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Retry transient HTTP failures with bounded server-directed backoff."""

        transient_statuses = {429, 500, 502, 503, 504}
        for attempt in range(1, self._max_attempts + 1):
            try:
                return await self._post(payload)
            except httpx.HTTPStatusError as error:
                status_code = error.response.status_code
                retryable = status_code in transient_statuses
                if retryable and attempt < self._max_attempts:
                    retry_after = error.response.headers.get("Retry-After")
                    try:
                        delay = max(0.0, float(retry_after)) if retry_after else 2 ** (attempt - 1)
                    except ValueError:
                        delay = 2 ** (attempt - 1)
                    await asyncio.sleep(min(delay, 30.0))
                    continue
                message = self._safe_http_error(error.response)
                error_type = GeminiRateLimitError if status_code == 429 else GeminiAPIError
                raise error_type(message, status_code=status_code,
                                 retryable=retryable) from error
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt < self._max_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 30.0))
                    continue
                raise GeminiAPIError(
                    "Gemini is temporarily unreachable after retrying",
                    status_code=503, retryable=True,
                ) from error
        raise AssertionError("unreachable")

    @staticmethod
    def _safe_http_error(response: httpx.Response) -> str:
        """Return bounded vendor diagnostics without headers, keys, or request data."""

        detail = ""
        try:
            body = response.json()
            error = body.get("error", body) if isinstance(body, dict) else {}
            if isinstance(error, dict):
                detail = str(error.get("message", "")).strip()
            elif isinstance(error, str):
                detail = error.strip()
        except (ValueError, TypeError):
            pass
        prefix = ("Gemini rate limit or quota exhausted" if response.status_code == 429
                  else f"Gemini request failed with status {response.status_code}")
        return f"{prefix}: {detail[:300]}" if detail else prefix

    def _metadata(self, component: str, request_id: str | None, *,
                  prompt_version: str | None = None) -> ProviderMetadata:
        return ProviderMetadata(provider="gemini", model=self._model,
            prompt_version=prompt_version or f"{component}-v1", request_id=request_id, stub=False)


def _gemini_schema(output_type: type[BaseModel]) -> dict[str, Any]:
    """Convert Pydantic JSON Schema into Gemini's smaller supported subset."""

    source = output_type.model_json_schema()
    definitions = source.get("$defs", {})

    def clean(value: Any) -> Any:
        if isinstance(value, list):
            return [clean(item) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            name = value["$ref"].removeprefix("#/$defs/")
            return clean(deepcopy(definitions[name]))
        cleaned = {key: clean(item) for key, item in value.items()
                   if key not in {"$defs", "title", "default", "maxItems", "minItems",
                                  "maxLength", "minLength", "maximum", "minimum"}}
        if "const" in cleaned:
            cleaned["enum"] = [cleaned.pop("const")]
        return cleaned

    return clean(source)


class GeminiFilterProvider(_GeminiStructuredProvider, FilterProviderBehavior):
    """Classify canonical evidence through Gemini structured output."""


class GeminiInterpreterProvider(_GeminiStructuredProvider, InterpreterProviderBehavior):
    """Extract ungrounded signal proposals through Gemini structured output."""


class GeminiRiskProvider(_GeminiStructuredProvider, RiskProviderBehavior):
    """Generate bounded risk scenarios through Gemini structured output."""


class GeminiPlannerProvider(_GeminiStructuredProvider, PlannerProviderBehavior):
    """Generate bounded intervention plans through Gemini structured output."""


class GeminiPlannerPanelProvider:
    """Run a bounded panel of role-specialized Gemini planners concurrently."""

    roles = (
        ("continuity", "Prioritize operational continuity and service recovery."),
        ("cost", "Prioritize resource efficiency and cost control."),
        ("resilience", "Prioritize robust mitigation under uncertainty."),
        ("responsiveness", "Prioritize speed of implementation and near-term risk reduction."),
        ("sustainability", "Prioritize durable and environmentally responsible mitigation."),
    )

    def __init__(self, *, api_key: str, model: str = "gemini-flash-lite-latest",
                 max_attempts: int = 3, timeout_seconds: float = 30,
                 client: httpx.AsyncClient | None = None,
                 agent_prompts: list[str] | None = None,
                 agent_count: int = 3) -> None:
        if not 1 <= agent_count <= 5:
            raise ValueError("Panel agent count must be between 1 and 5")
        if agent_prompts is not None and len(agent_prompts) < agent_count:
            raise ValueError("A system prompt is required for every panel agent")
        self._model = model
        self._planners = [
            (role, GeminiPlannerProvider(api_key=api_key, model=model,
                max_attempts=max_attempts, timeout_seconds=timeout_seconds, client=client,
                system_prompt=((agent_prompts[index] + "\n\n") if agent_prompts else "")
                + f"Panel role: {role}. {directive} Produce exactly one distinct proposal."))
            for index, (role, directive) in enumerate(self.roles[:agent_count])
        ]

    async def propose_plans(self, request: PlannerRequest) -> PlannerResponse:
        active = self._planners[:request.proposal_limit]
        metadata = ProviderMetadata(provider="gemini-panel", model=self._model,
            prompt_version="panel-v1", stub=False)
        if not active:
            return PlannerResponse(metadata=metadata)

        role_request = request.model_copy(update={"proposal_limit": 1})
        results = await asyncio.gather(*(
            planner.propose_plans(role_request) for _, planner in active))
        proposals: list[PlanProposal] = []
        warnings: list[str] = []
        for (role, _), result in zip(active, results):
            warnings.extend(f"{role}: {warning}" for warning in result.warnings)
            for proposal in result.proposals[:1]:
                role_metadata = proposal.metadata.model_copy(update={
                    "provider": "gemini-panel", "prompt_version": f"panel-{role}-v1"})
                proposals.append(proposal.model_copy(update={
                    "proposal_id": f"{role}-{proposal.proposal_id}"[:120],
                    "metadata": role_metadata,
                }))
        return PlannerResponse(proposals=proposals, warnings=warnings[:100], metadata=metadata)


_json_object = json_object


class GeminiHypothesisProvider(_GeminiStructuredProvider, HypothesisProviderBehavior):
    """Generate review-only hypothetical signals through Gemini structured output."""
