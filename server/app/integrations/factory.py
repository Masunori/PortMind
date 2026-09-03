"""The only module allowed to select gateways and purpose-specific providers."""

import os

from app.integrations.bedrock import (
    BedrockFilterProvider, BedrockHypothesisProvider, BedrockInterpreterProvider,
    BedrockPlannerPanelProvider, BedrockPlannerProvider, BedrockRiskProvider,
)
from app.integrations.gateway import ClientGateway, HTTPClientGateway
from app.integrations.gemini import (
    GeminiFilterProvider, GeminiHypothesisProvider, GeminiInterpreterProvider,
    GeminiPlannerPanelProvider, GeminiPlannerProvider, GeminiRiskProvider,
)
from app.integrations.providers import (
    ProviderBundle, StubEffectMappingProvider, StubFilterProvider,
    StubInterpreterProvider, StubRelationshipProvider,
    HypothesisProvider, PlannerProvider, RiskProvider, StubHypothesisProvider,
    StubPlannerPanelProvider, StubPlannerProvider, StubRiskProvider,
)
from app.services.prompt_service import get_prompt


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default).strip().casefold()


def _gemini_settings() -> dict[str, object]:
    return dict(api_key=os.getenv("GEMINI_API_KEY", ""),
        model=os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip(),
        max_attempts=int(os.getenv("GEMINI_MAX_ATTEMPTS", "3")),
        timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "30")))


def _bedrock_settings() -> dict[str, object]:
    return dict(
        model=os.getenv("BEDROCK_MODEL_ID", "").strip(),
        region=(os.getenv("BEDROCK_REGION") or os.getenv("AWS_REGION")
                or os.getenv("AWS_DEFAULT_REGION")),
        max_attempts=int(os.getenv("BEDROCK_MAX_ATTEMPTS", "3")),
        timeout_seconds=float(os.getenv("BEDROCK_TIMEOUT_SECONDS", "60")),
        max_tokens=int(os.getenv("BEDROCK_MAX_TOKENS", "4096")),
        sdk_max_attempts=int(os.getenv("BEDROCK_SDK_MAX_ATTEMPTS", "2")),
    )


def get_provider_bundle() -> ProviderBundle:
    """Build provider adapters from centralized configuration."""

    configured = {
        "FILTER_PROVIDER": _setting("FILTER_PROVIDER", "stub"),
        "INTERPRETER_PROVIDER": _setting("INTERPRETER_PROVIDER", "stub"),
        "EFFECT_MAPPING_PROVIDER": _setting("EFFECT_MAPPING_PROVIDER", "stub"),
        "RELATIONSHIP_PROVIDER": _setting("RELATIONSHIP_PROVIDER", "stub"),
    }
    allowed = {
        "FILTER_PROVIDER": {"stub", "gemini", "bedrock"},
        "INTERPRETER_PROVIDER": {"stub", "gemini", "bedrock"},
        "EFFECT_MAPPING_PROVIDER": {"stub"},
        "RELATIONSHIP_PROVIDER": {"stub"},
    }
    unsupported = [f"{key}={value}" for key, value in configured.items()
                   if value not in allowed[key]]
    if unsupported:
        raise ValueError(f"Unsupported provider configuration: {', '.join(unsupported)}")
    gemini_settings = _gemini_settings()
    bedrock_settings = _bedrock_settings()
    filter_provider = (
        GeminiFilterProvider(**gemini_settings, system_prompt=get_prompt("filter"))
        if configured["FILTER_PROVIDER"] == "gemini" else
        BedrockFilterProvider(**bedrock_settings, system_prompt=get_prompt("filter"))
        if configured["FILTER_PROVIDER"] == "bedrock" else StubFilterProvider()
    )
    interpreter_provider = (
        GeminiInterpreterProvider(**gemini_settings, system_prompt=get_prompt("interpreter"))
        if configured["INTERPRETER_PROVIDER"] == "gemini" else
        BedrockInterpreterProvider(**bedrock_settings, system_prompt=get_prompt("interpreter"))
        if configured["INTERPRETER_PROVIDER"] == "bedrock" else StubInterpreterProvider()
    )
    return ProviderBundle(filter=filter_provider, interpreter=interpreter_provider,
                          effect_mapping=StubEffectMappingProvider(), relationship=StubRelationshipProvider())


def get_client_gateway() -> ClientGateway:
    """Build the HTTP-only runtime gateway without exposing settings downstream."""

    url = os.getenv("CLIENT_GATEWAY_URL", "").strip()
    if not url:
        raise ValueError("CLIENT_GATEWAY_URL is required; runtime client access is HTTP-only")
    return HTTPClientGateway(url, token=os.getenv("CLIENT_GATEWAY_TOKEN"),
                             timeout_seconds=float(os.getenv("CLIENT_GATEWAY_TIMEOUT_SECONDS", "10")),
                             max_retries=int(os.getenv("CLIENT_GATEWAY_MAX_RETRIES", "2")))


def get_risk_provider() -> RiskProvider:
    name = _setting("RISK_PROVIDER", "stub")
    if name == "stub": return StubRiskProvider()
    if name == "gemini": return GeminiRiskProvider(**_gemini_settings())
    if name == "bedrock": return BedrockRiskProvider(**_bedrock_settings())
    raise ValueError(f"Unsupported provider configuration: RISK_PROVIDER={name}")


def get_planner_provider(mode: str = "single", panel_agent_count: int = 3) -> PlannerProvider:
    name = _setting("PLANNER_PROVIDER", "stub")
    if mode == "panel" and name == "stub": return StubPlannerPanelProvider(panel_agent_count)
    if mode == "panel" and name == "gemini":
        prompts = [get_prompt(f"planner_{index}") for index in range(1, panel_agent_count + 1)]
        return GeminiPlannerPanelProvider(**_gemini_settings(), agent_prompts=prompts,
                                          agent_count=panel_agent_count)
    if mode == "panel" and name == "bedrock":
        prompts = [get_prompt(f"planner_{index}") for index in range(1, panel_agent_count + 1)]
        return BedrockPlannerPanelProvider(**_bedrock_settings(), agent_prompts=prompts,
                                           agent_count=panel_agent_count)
    if mode != "single": raise ValueError(f"Unsupported planner mode: {mode}")
    if name == "stub": return StubPlannerProvider()
    if name == "gemini": return GeminiPlannerProvider(**_gemini_settings(), system_prompt=get_prompt("planner"))
    if name == "bedrock": return BedrockPlannerProvider(**_bedrock_settings(), system_prompt=get_prompt("planner"))
    raise ValueError(f"Unsupported provider configuration: PLANNER_PROVIDER={name}")


def get_hypothesis_provider() -> HypothesisProvider:
    default = "bedrock" if os.getenv("BEDROCK_MODEL_ID", "").strip() else "stub"
    name = _setting("HYPOTHESIS_PROVIDER", default)
    if name == "stub": return StubHypothesisProvider()
    if name == "gemini": return GeminiHypothesisProvider(**_gemini_settings())
    if name == "bedrock": return BedrockHypothesisProvider(**_bedrock_settings())
    raise ValueError(f"Unsupported provider configuration: HYPOTHESIS_PROVIDER={name}")
