"""Structural interface implemented by every AI provider adapter."""

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AIProvider(Protocol):
    """Generate validated structured output without exposing a vendor SDK."""

    async def structured_generate(
        self,
        prompt: str,
        output_type: type[T],
    ) -> T:
        """Generate one response parsed as the requested Pydantic model."""

        ...
