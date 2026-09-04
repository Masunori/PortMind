"""Typed boundaries between the platform, providers, and client systems."""

__all__ = ["get_client_gateway", "get_provider_bundle", "get_risk_provider",
           "get_planner_provider", "get_hypothesis_provider"]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    from app.integrations import factory
    return getattr(factory, name)
