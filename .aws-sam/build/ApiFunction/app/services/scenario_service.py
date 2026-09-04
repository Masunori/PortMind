"""Scenario workflows backed by a storage-neutral repository."""
from app.domain.scenario import Scenario
from app.repositories.contracts import ScenarioRepository
from app.repositories import get_scenario_repository

def _repo(repository: ScenarioRepository | None = None) -> ScenarioRepository: return repository or get_scenario_repository()
def save_scenario(scenario: Scenario, repository: ScenarioRepository | None = None) -> Scenario: return _repo(repository).save(scenario)
def get_scenarios(repository: ScenarioRepository | None = None) -> list[Scenario]: return list(_repo(repository).list(limit=1000).items)
def get_scenario(scenario_id: str, repository: ScenarioRepository | None = None) -> Scenario | None: return _repo(repository).get(scenario_id)
