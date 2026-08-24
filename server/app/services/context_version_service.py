"""Monotonic invalidation for graph-, schema-, alias-, and taxonomy-aware context."""

from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import NetworkContextStateRecord


def bump_context_version(session=None) -> int:
    """Increment the context version in an existing or owned transaction."""

    owns = session is None
    active = SessionLocal() if owns else session
    try:
        record = active.get(NetworkContextStateRecord, 1)
        if record is None:
            record = NetworkContextStateRecord(
                id=1, version=1, updated_at=datetime.now(timezone.utc)
            )
            active.add(record)
        else:
            record.version += 1
            record.updated_at = datetime.now(timezone.utc)
        if owns:
            active.commit()
        return record.version
    finally:
        if owns:
            active.close()


def get_context_version() -> int:
    """Return the current context version, initializing it when absent."""

    with SessionLocal() as session:
        record = session.get(NetworkContextStateRecord, 1)
    return record.version if record else bump_context_version()
