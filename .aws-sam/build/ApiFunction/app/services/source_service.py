"""Source workflows backed by a storage-neutral repository."""
from datetime import datetime
from app.domain.source import DataSource, DataSourceCreate, DataSourceUpdate
from app.repositories.contracts import SourceRepository
from app.repositories.errors import ConflictError, NotFoundError
from app.repositories import get_source_repository

def _repo(repository: SourceRepository | None = None) -> SourceRepository: return repository or get_source_repository()
def create_source(values: DataSourceCreate, repository: SourceRepository | None = None) -> DataSource: return _repo(repository).create(values)
def get_sources(repository: SourceRepository | None = None) -> list[DataSource]: return list(_repo(repository).list(limit=1000).items)
def get_source(source_id: str, repository: SourceRepository | None = None) -> DataSource | None: return _repo(repository).get(source_id)
def update_source(source_id: str, values: DataSourceUpdate, repository: SourceRepository | None = None) -> DataSource | None: return _repo(repository).update(source_id, values)
def delete_source(source_id: str, repository: SourceRepository | None = None) -> bool:
    try: return _repo(repository).delete(source_id)
    except ConflictError as error: raise PermissionError(str(error)) from error
def get_due_sources(now: datetime | None = None, repository: SourceRepository | None = None) -> list[DataSource]: return _repo(repository).due(now)
def record_source_run(source_id: str, error: str | None = None, repository: SourceRepository | None = None) -> DataSource:
    try: return _repo(repository).record_run(source_id, error)
    except NotFoundError as missing: raise LookupError(str(missing)) from missing
