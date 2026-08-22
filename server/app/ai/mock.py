"""Deterministic fixture-backed AI provider for local development and tests."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from app.ai.base import T
from app.ai.schemas import DisruptionSignal, InterpretedSignal

FixtureMap = Mapping[type[BaseModel], Mapping[str, Any]]
PromptFixtureMap = Mapping[
    type[BaseModel],
    tuple[tuple[str, Mapping[str, Any]], ...],
]

DEFAULT_FIXTURES: FixtureMap = {
    DisruptionSignal: {
        "event_type": "WEATHER_DISRUPTION",
        "location": "Hai Phong",
        "duration_min_hours": 48,
        "duration_max_hours": 72,
        "confidence": 0.8,
    },
    InterpretedSignal: {
        "event_type": "UNKNOWN",
        "locations": [],
        "expected_duration_min_hours": None,
        "expected_duration_max_hours": None,
        "severity": None,
        "confidence": 0,
    },
}

DEFAULT_PROMPT_FIXTURES: PromptFixtureMap = {
    InterpretedSignal: (
        (
            "typhoon may disrupt hai phong for 2–3 days",
            {
                "event_type": "WEATHER_DISRUPTION",
                "locations": ["Hai Phong"],
                "expected_duration_min_hours": 48,
                "expected_duration_max_hours": 72,
                "severity": 0.7,
                "confidence": 0.8,
            },
        ),
    )
}


class MockAIProvider:
    """Return validated copies of configured fixtures without external calls."""

    def __init__(
        self,
        fixtures: FixtureMap | None = None,
        prompt_fixtures: PromptFixtureMap | None = None,
    ) -> None:
        """Initialize the provider with optional output-type fixtures."""

        self._fixtures = fixtures if fixtures is not None else DEFAULT_FIXTURES
        self._prompt_fixtures = (
            prompt_fixtures
            if prompt_fixtures is not None
            else DEFAULT_PROMPT_FIXTURES
        )

    async def structured_generate(
        self,
        prompt: str,
        output_type: type[T],
    ) -> T:
        """Return the deterministic fixture registered for ``output_type``."""

        normalized_prompt = " ".join(prompt.casefold().split())
        fixture = next(
            (
                candidate
                for text, candidate in self._prompt_fixtures.get(output_type, ())
                if " ".join(text.casefold().split()) in normalized_prompt
            ),
            self._fixtures.get(output_type),
        )
        if fixture is None:
            raise ValueError(
                f"MockAIProvider has no fixture for {output_type.__name__}"
            )
        return output_type.model_validate(fixture)
