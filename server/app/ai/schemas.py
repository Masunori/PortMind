"""Validated structured-output schemas shared across AI providers."""

from pydantic import BaseModel, Field, model_validator


class DisruptionSignal(BaseModel):
    """Represent a disruption signal extracted from unstructured text."""

    event_type: str
    location: str
    duration_min_hours: float = Field(ge=0)
    duration_max_hours: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_duration_range(self) -> "DisruptionSignal":
        """Require the maximum duration to be at least the minimum."""

        if self.duration_max_hours < self.duration_min_hours:
            raise ValueError("Maximum duration must not be below minimum duration")
        return self


class InterpretedSignal(BaseModel):
    """Represent an operational event interpreted from an external signal."""

    event_type: str
    locations: list[str]
    expected_duration_min_hours: int | None = Field(default=None, ge=0)
    expected_duration_max_hours: int | None = Field(default=None, ge=0)
    severity: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_expected_duration(self) -> "InterpretedSignal":
        """Require a complete and increasing optional duration range."""

        minimum = self.expected_duration_min_hours
        maximum = self.expected_duration_max_hours
        if (minimum is None) != (maximum is None):
            raise ValueError("Expected duration requires both minimum and maximum")
        if minimum is not None and maximum is not None and maximum < minimum:
            raise ValueError("Maximum duration must not be below minimum duration")
        return self


class RelevanceAssessment(BaseModel):
    """Provider assessment of operational relevance to the current network."""

    relevance_probability: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)
    matched_entities: list[str] = Field(default_factory=list)


class DisruptionExtraction(BaseModel):
    """Human-readable disruption facts proposed from one relevant document."""

    disruption_type: str
    affected_locations: list[str] = Field(min_length=1)
    start_time_hours: float = Field(ge=0)
    end_time_hours: float = Field(gt=0)
    probability: float
    severity: float
    effects: dict[str, object]
    summary: str = Field(min_length=1)
    confidence: float
