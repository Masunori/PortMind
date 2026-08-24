"""Declarative simulation-rule endpoints."""

from fastapi import APIRouter, HTTPException
from app.domain.rule import SimulationRule, SimulationRuleCreate
from app.services.rule_service import get_rules, save_rule

router = APIRouter(prefix="/api/simulation-rules", tags=["simulation rules"])


@router.get("", response_model=list[SimulationRule])
def rules() -> list[SimulationRule]:
    """List declarative simulation rules in stable order."""

    return get_rules()


@router.post("", response_model=SimulationRule, status_code=201)
def add_rule(values: SimulationRuleCreate) -> SimulationRule:
    """Validate and persist one non-executable simulation rule."""

    try:
        return save_rule(values)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
