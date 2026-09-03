"""Operator endpoints for agent system-prompt configuration."""

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.services.prompt_service import (
    AgentName, AgentPrompt, AgentPromptUpdate, list_prompts, reset_prompt, save_prompt,
)

router = APIRouter(prefix="/api/settings/prompts", tags=["settings"])


@router.get("", response_model=list[AgentPrompt])
def prompts() -> list[AgentPrompt]:
    return list_prompts()


@router.put("/{agent}", response_model=AgentPrompt)
def update_prompt(agent: AgentName, values: AgentPromptUpdate) -> AgentPrompt:
    try:
        return save_prompt(agent, values.prompt)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="Prompt settings storage is unavailable; apply database migrations and retry",
        ) from error


@router.delete("/{agent}", response_model=AgentPrompt)
def restore_prompt(agent: AgentName) -> AgentPrompt:
    try:
        return reset_prompt(agent)
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=503,
            detail="Prompt settings storage is unavailable; apply database migrations and retry",
        ) from error
