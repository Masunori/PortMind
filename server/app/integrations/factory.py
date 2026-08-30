"""The only module allowed to select gateways and purpose-specific providers."""

import os

from app.integrations.gateway import ClientGateway, HTTPClientGateway
from app.integrations.gemini import (
    GeminiFilterProvider, GeminiHypothesisProvider, GeminiInterpreterProvider,
)
from app.integrations.providers import (
    ProviderBundle, StubEffectMappingProvider, StubFilterProvider,
    StubInterpreterProvider, StubRelationshipProvider,
    HypothesisProvider, PlannerProvider, RiskProvider, StubHypothesisProvider,
    StubPlannerPanelProvider, StubPlannerProvider, StubRiskProvider,
)


def _setting(name: str, default: str) -> str:
    return os.getenv(name, default).strip().casefold()


def get_provider_bundle() -> ProviderBundle:
    """Build provider adapters from centralized configuration."""

    configured = {
        "FILTER_PROVIDER": _setting("FILTER_PROVIDER", "stub"),
        "INTERPRETER_PROVIDER": _setting("INTERPRETER_PROVIDER", "stub"),
        "EFFECT_MAPPING_PROVIDER": _setting("EFFECT_MAPPING_PROVIDER", "stub"),
        "RELATIONSHIP_PROVIDER": _setting("RELATIONSHIP_PROVIDER", "stub"),
    }
    allowed = {
        "FILTER_PROVIDER": {"stub", "gemini"},
        "INTERPRETER_PROVIDER": {"stub", "gemini"},
        "EFFECT_MAPPING_PROVIDER": {"stub"},
        "RELATIONSHIP_PROVIDER": {"stub"},
    }
    unsupported = [f"{key}={value}" for key, value in configured.items()
                   if value not in allowed[key]]
    if unsupported:
        raise ValueError(f"Unsupported provider configuration: {', '.join(unsupported)}")
    gemini_settings = dict(api_key=os.getenv("GEMINI_API_KEY", ""),
        model=os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip(),
        max_attempts=int(os.getenv("GEMINI_MAX_ATTEMPTS", "3")),
        timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "30")))
    filter_provider = (GeminiFilterProvider(**gemini_settings)
                       if configured["FILTER_PROVIDER"] == "gemini" else StubFilterProvider())
    interpreter_provider = (GeminiInterpreterProvider(**gemini_settings)
                            if configured["INTERPRETER_PROVIDER"] == "gemini"
                            else StubInterpreterProvider())
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
    if name != "stub": raise ValueError(f"Unsupported provider configuration: RISK_PROVIDER={name}")
    return StubRiskProvider()


def get_planner_provider(mode: str = "single") -> PlannerProvider:
    if mode == "panel": return StubPlannerPanelProvider()
    if mode != "single": raise ValueError(f"Unsupported planner mode: {mode}")
    name = _setting("PLANNER_PROVIDER", "stub")
    if name != "stub": raise ValueError(f"Unsupported provider configuration: PLANNER_PROVIDER={name}")
    return StubPlannerProvider()


def get_hypothesis_provider() -> HypothesisProvider:
    default = "gemini" if os.getenv("GEMINI_API_KEY", "").strip() else "stub"
    name = _setting("HYPOTHESIS_PROVIDER", default)
    if name == "stub": return StubHypothesisProvider()
    if name != "gemini":
        raise ValueError(f"Unsupported provider configuration: HYPOTHESIS_PROVIDER={name}")
    return GeminiHypothesisProvider(api_key=os.getenv("GEMINI_API_KEY", ""),
        model=os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest").strip(),
        max_attempts=int(os.getenv("GEMINI_MAX_ATTEMPTS", "3")),
        timeout_seconds=float(os.getenv("GEMINI_TIMEOUT_SECONDS", "30")))
