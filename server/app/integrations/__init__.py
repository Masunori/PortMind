"""Typed boundaries between the platform, providers, and client systems."""

from app.integrations.factory import (
    get_client_gateway, get_hypothesis_provider, get_planner_provider,
    get_provider_bundle, get_risk_provider,
)

__all__ = ["get_client_gateway", "get_provider_bundle", "get_risk_provider",
           "get_planner_provider", "get_hypothesis_provider"]
