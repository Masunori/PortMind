"""Interpret unstructured event signals through the AI provider boundary."""

from pydantic import BaseModel, field_validator

from app.ai import AIProvider, get_ai_provider
from app.ai.schemas import InterpretedSignal
from app.domain.grounding import GroundedSignal
from app.services.entity_resolution import ground_interpreted_signal


class InterpretSignalRequest(BaseModel):
    """Request containing one unstructured event signal."""

    text: str

    @field_validator("text")
    @classmethod
    def require_text(cls, value: str) -> str:
        """Trim the signal and reject empty or whitespace-only input."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("Signal text must not be empty")
        return normalized


class EventInterpreter:
    """Convert unstructured text into a validated operational event."""

    def __init__(self, provider: AIProvider) -> None:
        """Initialize the interpreter with a provider abstraction."""

        self._provider = provider

    async def interpret(
        self,
        request: InterpretSignalRequest,
    ) -> InterpretedSignal:
        """Interpret one signal using structured provider generation."""

        return await self._provider.structured_generate(
            request.text,
            InterpretedSignal,
        )

    async def interpret_and_ground(
        self,
        request: InterpretSignalRequest,
    ) -> GroundedSignal:
        """Interpret text and resolve its locations to persisted graph IDs."""

        signal = await self.interpret(request)
        return ground_interpreted_signal(signal)


def get_event_interpreter() -> EventInterpreter:
    """Build an interpreter using the configured provider dependency."""

    return EventInterpreter(get_ai_provider())


__all__ = [
    "EventInterpreter",
    "InterpretSignalRequest",
    "InterpretedSignal",
    "get_event_interpreter",
]
