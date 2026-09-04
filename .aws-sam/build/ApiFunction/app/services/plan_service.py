"""Plan workflows backed by a storage-neutral repository."""
from app.domain.plan import Plan, PlanStatus
from app.repositories.contracts import PlanRepository
from app.repositories import get_plan_repository

def _repo(repository: PlanRepository | None = None) -> PlanRepository: return repository or get_plan_repository()
def save_plan(plan: Plan, repository: PlanRepository | None = None) -> Plan: return _repo(repository).save(plan)
def get_plans(repository: PlanRepository | None = None) -> list[Plan]: return list(_repo(repository).list(limit=1000).items)
def set_plan_status(plan_id: str, status: PlanStatus, repository: PlanRepository | None = None) -> Plan | None: return _repo(repository).set_status(plan_id, status)
