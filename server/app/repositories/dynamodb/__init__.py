"""DynamoDB persistence primitives and repository adapters."""

from app.repositories.dynamodb.client import get_table, reset_clients
from app.repositories.dynamodb.config import DynamoSettings
from app.repositories.dynamodb.schema import TABLE_SCHEMA, create_table, delete_table

__all__ = [
    "DynamoSettings", "TABLE_SCHEMA", "create_table", "delete_table", "get_table",
    "reset_clients",
    "DynamoSourceRepository", "DynamoEvidenceRepository", "DynamoPromptRepository",
    "DynamoScenarioRepository", "DynamoPlanRepository", "DynamoSignalRepository",
    "DynamoExperimentRepository", "DynamoPlanningCycleRepository",
]

_ADAPTER_MODULES = {
    "DynamoSourceRepository": "source", "DynamoEvidenceRepository": "evidence",
    "DynamoPromptRepository": "definitions", "DynamoScenarioRepository": "definitions",
    "DynamoPlanRepository": "definitions", "DynamoSignalRepository": "signal",
    "DynamoExperimentRepository": "experiment", "DynamoPlanningCycleRepository": "planning",
}


def __getattr__(name: str):
    """Load adapters lazily so foundational imports cannot create domain cycles."""
    module_name = _ADAPTER_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    from importlib import import_module
    return getattr(import_module(f"app.repositories.dynamodb.{module_name}"), name)
