"""Tests for AI-provider-based event signal interpretation."""

import asyncio

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.agents.interpreter import (
    EventInterpreter,
    InterpretSignalRequest,
    InterpretedSignal,
    get_event_interpreter,
)
from app.ai import MockAIProvider
from app.seed import seed


def test_interpreter_matches_known_typhoon_demo() -> None:
    """The known Hai Phong signal returns its deterministic interpretation."""

    interpreter = EventInterpreter(MockAIProvider())
    request = InterpretSignalRequest(
        text="Typhoon may disrupt Hai Phong for 2–3 days"
    )

    result = asyncio.run(interpreter.interpret(request))

    assert result == InterpretedSignal(
        event_type="WEATHER_DISRUPTION",
        locations=["Hai Phong"],
        expected_duration_min_hours=48,
        expected_duration_max_hours=72,
        severity=0.7,
        confidence=0.8,
    )


def test_interpreter_returns_stable_fallback_for_unknown_signal() -> None:
    """Unknown demo text remains deterministic without inventing details."""

    interpreter = EventInterpreter(MockAIProvider())

    result = asyncio.run(
        interpreter.interpret(InterpretSignalRequest(text="Unrecognized report"))
    )

    assert result.event_type == "UNKNOWN"
    assert result.locations == []
    assert result.expected_duration_min_hours is None
    assert result.expected_duration_max_hours is None
    assert result.severity is None
    assert result.confidence == 0


def test_interpreter_requests_the_typed_provider_schema() -> None:
    """The interpreter passes text and output type only through AIProvider."""

    class RecordingProvider:
        """Record one structured-generation request for boundary verification."""

        def __init__(self) -> None:
            """Initialize without a recorded request."""

            self.request: tuple[str, type[InterpretedSignal]] | None = None

        async def structured_generate(
            self,
            prompt: str,
            output_type: type[InterpretedSignal],
        ) -> InterpretedSignal:
            """Record the call and return a validated fixture."""

            self.request = (prompt, output_type)
            return output_type(
                event_type="PORT_CLOSURE",
                locations=["PSA Singapore"],
                expected_duration_min_hours=12,
                expected_duration_max_hours=12,
                severity=0.5,
                confidence=0.9,
            )

    provider = RecordingProvider()
    interpreter = EventInterpreter(provider)
    request = InterpretSignalRequest(text="  Port closure report  ")

    result = asyncio.run(interpreter.interpret(request))

    assert provider.request == ("Port closure report", InterpretedSignal)
    assert result.event_type == "PORT_CLOSURE"


def test_interpret_request_rejects_blank_text() -> None:
    """Whitespace-only signals are rejected before calling a provider."""

    with pytest.raises(ValidationError):
        InterpretSignalRequest(text="   ")


def test_interpreted_signal_validates_optional_duration_pair() -> None:
    """An interpreted duration cannot contain only one range endpoint."""

    with pytest.raises(ValidationError):
        InterpretedSignal(
            event_type="WEATHER_DISRUPTION",
            locations=["Hai Phong"],
            expected_duration_min_hours=48,
            expected_duration_max_hours=None,
            severity=0.7,
            confidence=0.8,
        )


def test_interpreter_dependency_uses_configured_provider() -> None:
    """The interpreter dependency is usable without a model account."""

    assert isinstance(get_event_interpreter(), EventInterpreter)


def test_interpreter_can_ground_mock_output_end_to_end(
    test_session_factory: sessionmaker[Session],
) -> None:
    """The complete flow resolves mock names only to persisted graph IDs."""

    seed()
    interpreter = EventInterpreter(MockAIProvider())

    grounded = asyncio.run(
        interpreter.interpret_and_ground(
            InterpretSignalRequest(
                text="Typhoon may disrupt Hai Phong for 2–3 days"
            )
        )
    )

    assert grounded.node_ids == ["hai-phong-port"]
    assert grounded.shipment_ids == ["shipment-001", "shipment-002"]
    assert grounded.unresolved_locations == []
