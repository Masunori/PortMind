"""Provider-neutral AI generation dependency."""

from app.ai.base import AIProvider
from app.ai.mock import MockAIProvider


def get_ai_provider() -> AIProvider:
    """Return the configured AI provider for application dependencies."""

    return MockAIProvider()


__all__ = ["AIProvider", "MockAIProvider", "get_ai_provider"]
