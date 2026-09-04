"""Storage-neutral operator prompt settings."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AgentName = Literal[
    "filter", "interpreter", "planner",
    "planner_1", "planner_2", "planner_3", "planner_4", "planner_5",
]


class AgentPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: AgentName
    prompt: str
    is_custom: bool
    updated_at: datetime | None = None


class AgentPromptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=20_000)
