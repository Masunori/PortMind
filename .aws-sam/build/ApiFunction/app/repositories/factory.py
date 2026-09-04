"""Explicit persistence-backend selection without fallback or dual writes."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os

from app.repositories.errors import UnavailableError
from app.repositories.contracts import EvidenceRepository, ExperimentRepository, PlanRepository, PlanningCycleRepository, PromptRepository, ScenarioRepository, SignalRepository, SourceRepository


SUPPORTED_BACKENDS = frozenset({"postgres", "dynamodb"})


@dataclass(frozen=True, slots=True)
class Storage:
    """Application persistence composition root."""

    backend: str

    def check_health(self) -> None:
        if self.backend == "dynamodb":
            try:
                from app.repositories.dynamodb import get_table
                get_table().load()
                return
            except Exception as error:
                raise UnavailableError("storage unavailable") from error
        try:
            # Imported lazily so an eventual DynamoDB Lambda does not initialize SQLAlchemy.
            from app.database import engine
            from sqlalchemy import text
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as error:
            raise UnavailableError("storage unavailable") from error


def selected_backend() -> str:
    backend = os.getenv("PERSISTENCE_BACKEND", "postgres").strip().lower()
    if backend not in SUPPORTED_BACKENDS:
        choices = ", ".join(sorted(SUPPORTED_BACKENDS))
        raise RuntimeError(
            f"Unsupported PERSISTENCE_BACKEND={backend!r}; implemented values: {choices}"
        )
    if backend == "dynamodb":
        from app.repositories.dynamodb.config import DynamoSettings
        DynamoSettings.from_environment()
    if backend == "postgres" and not os.getenv("DATABASE_URL"):
        # Local development deliberately retains database.py's Compose-compatible default.
        return backend
    return backend


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    return Storage(backend=selected_backend())


def reset_storage() -> None:
    """Clear cached composition; intended for isolated configuration tests."""

    get_storage.cache_clear()


def get_source_repository() -> SourceRepository:
    if selected_backend() == "dynamodb":
        from app.repositories.dynamodb import DynamoSourceRepository
        return DynamoSourceRepository()
    from app.repositories.postgres import PostgresSourceRepository
    return PostgresSourceRepository()


def get_evidence_repository() -> EvidenceRepository:
    if selected_backend() == "dynamodb":
        from app.repositories.dynamodb import DynamoEvidenceRepository
        return DynamoEvidenceRepository()
    from app.repositories.postgres import PostgresEvidenceRepository
    return PostgresEvidenceRepository()

def get_experiment_repository() -> ExperimentRepository:
    if selected_backend() == "dynamodb":
        from app.repositories.dynamodb import DynamoExperimentRepository
        return DynamoExperimentRepository()
    from app.repositories.postgres import PostgresExperimentRepository
    return PostgresExperimentRepository()

def get_signal_repository() -> SignalRepository:
    if selected_backend() == "dynamodb":
        from app.repositories.dynamodb import DynamoSignalRepository
        return DynamoSignalRepository()
    from app.repositories.postgres import PostgresSignalRepository
    return PostgresSignalRepository()

def get_planning_cycle_repository() -> PlanningCycleRepository:
    if selected_backend() == "dynamodb":
        from app.repositories.dynamodb import DynamoPlanningCycleRepository
        return DynamoPlanningCycleRepository()
    from app.repositories.postgres import PostgresPlanningCycleRepository
    return PostgresPlanningCycleRepository()


def get_prompt_repository() -> PromptRepository:
    if selected_backend() == "dynamodb":
        from app.repositories.dynamodb import DynamoPromptRepository
        return DynamoPromptRepository()
    from app.repositories.postgres import PostgresPromptRepository
    return PostgresPromptRepository()


def get_scenario_repository() -> ScenarioRepository:
    if selected_backend() == "dynamodb":
        from app.repositories.dynamodb import DynamoScenarioRepository
        return DynamoScenarioRepository()
    from app.repositories.postgres import PostgresScenarioRepository
    return PostgresScenarioRepository()


def get_plan_repository() -> PlanRepository:
    if selected_backend() == "dynamodb":
        from app.repositories.dynamodb import DynamoPlanRepository
        return DynamoPlanRepository()
    from app.repositories.postgres import PostgresPlanRepository
    return PostgresPlanRepository()
