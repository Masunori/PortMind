"""Tests for the provider-neutral AI interface and deterministic mock."""

import asyncio

import pytest
from pydantic import BaseModel, ValidationError

from app.ai import AIProvider, MockAIProvider, get_ai_provider
from app.ai.schemas import DisruptionSignal


def test_mock_returns_deterministic_structured_disruption() -> None:
    """The example typhoon prompt produces the documented fixture output."""

    provider: AIProvider = MockAIProvider()
    prompt = "Typhoon may disrupt Hai Phong for 2–3 days"

    first = asyncio.run(provider.structured_generate(prompt, DisruptionSignal))
    second = asyncio.run(provider.structured_generate(prompt, DisruptionSignal))

    assert first == second
    assert first is not second
    assert first.model_dump() == {
        "event_type": "WEATHER_DISRUPTION",
        "location": "Hai Phong",
        "duration_min_hours": 48.0,
        "duration_max_hours": 72.0,
        "confidence": 0.8,
    }


def test_dependency_returns_mock_provider() -> None:
    """The dependency boundary selects the mock until a real adapter exists."""

    assert isinstance(get_ai_provider(), MockAIProvider)


def test_mock_accepts_custom_typed_fixtures() -> None:
    """Tests can inject deterministic fixtures for additional output schemas."""

    class Summary(BaseModel):
        """Minimal schema used to verify generic structured generation."""

        text: str

    provider = MockAIProvider({Summary: {"text": "fixture"}})

    result = asyncio.run(provider.structured_generate("ignored", Summary))

    assert result == Summary(text="fixture")


def test_mock_rejects_unregistered_output_type() -> None:
    """Missing fixtures fail clearly rather than fabricating output."""

    class UnknownOutput(BaseModel):
        """Unregistered output schema for the failure case."""

        value: str

    with pytest.raises(ValueError, match="no fixture"):
        asyncio.run(
            MockAIProvider().structured_generate("prompt", UnknownOutput)
        )


def test_disruption_signal_rejects_invalid_ranges() -> None:
    """Structured disruption output enforces duration and confidence bounds."""

    with pytest.raises(ValidationError):
        DisruptionSignal(
            event_type="WEATHER_DISRUPTION",
            location="Hai Phong",
            duration_min_hours=72,
            duration_max_hours=48,
            confidence=0.8,
        )
