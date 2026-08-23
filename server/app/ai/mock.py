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

DEFAULT_NAMED_FIXTURES: Mapping[str, Mapping[str, Any]] = {
    "ScenarioProposalBatch": {
        "proposals": [
            {
                "name": "24h closure",
                "probability": 0.45,
                "duration_hours": 24,
                "severity_multiplier": 2,
            },
            {
                "name": "48h closure",
                "probability": 0.35,
                "duration_hours": 48,
                "severity_multiplier": 2,
            },
            {
                "name": "72h closure",
                "probability": 0.15,
                "duration_hours": 72,
                "severity_multiplier": 2,
            },
            {
                "name": "120h closure",
                "probability": 0.05,
                "duration_hours": 120,
                "severity_multiplier": 2,
            },
        ]
    },
    "PlanProposalBatch": {
        "proposals": [
            {
                "name": "Wait",
                "rationale": "Allow the disruption window to pass.",
                "actions": [{"type": "WAIT"}],
            },
            {
                "name": "Reroute via Ho Chi Minh City",
                "rationale": "Avoid the affected Hai Phong route.",
                "actions": [
                    {
                        "type": "REROUTE_SHIPMENT",
                        "shipment_id": shipment_id,
                        "cost_multiplier": 3,
                        "new_route": [
                            "supplier-vn",
                            "ho-chi-minh-port",
                            "psa-singapore",
                            "singapore-warehouse",
                            "customer",
                        ],
                    }
                    for shipment_id in ("shipment-001", "shipment-002")
                ],
            },
            {
                "name": "Air-freight urgent inventory",
                "rationale": "Use the fastest direct transport mode.",
                "actions": [
                    {
                        "type": "EXPEDITE_SHIPMENT",
                        "shipment_id": shipment_id,
                        "new_route": [
                            "supplier-vn",
                            "psa-singapore",
                            "singapore-warehouse",
                            "customer",
                        ],
                    }
                    for shipment_id in ("shipment-001", "shipment-002")
                ],
            },
            {
                "name": "Partial air + sea",
                "rationale": "Balance speed and cost across the exposed shipments.",
                "actions": [
                    {
                        "type": "EXPEDITE_SHIPMENT",
                        "shipment_id": "shipment-001",
                        "new_route": [
                            "supplier-vn",
                            "psa-singapore",
                            "singapore-warehouse",
                            "customer",
                        ],
                    },
                    {
                        "type": "REROUTE_SHIPMENT",
                        "shipment_id": "shipment-002",
                        "new_route": [
                            "supplier-vn",
                            "ho-chi-minh-port",
                            "psa-singapore",
                            "singapore-warehouse",
                            "customer",
                        ],
                    },
                ],
            },
        ]
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
        (
            "severe weather may close hai phong for 2–3 days",
            {
                "event_type": "WEATHER_DISRUPTION",
                "locations": ["Hai Phong"],
                "expected_duration_min_hours": 48,
                "expected_duration_max_hours": 72,
                "severity": 0.7,
                "confidence": 0.8,
            },
        ),
        (
            "typhoon causes hai phong port disruption",
            {
                "event_type": "WEATHER_DISRUPTION",
                "locations": ["Hai Phong Port"],
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
            self._fixtures.get(output_type)
            or DEFAULT_NAMED_FIXTURES.get(output_type.__name__),
        )
        if fixture is None:
            raise ValueError(
                f"MockAIProvider has no fixture for {output_type.__name__}"
            )
        return output_type.model_validate(fixture)
