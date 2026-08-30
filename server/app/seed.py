"""Seed only platform-owned development fixtures."""

from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import DataSourceRecord


def seed() -> None:
    """Create a repeatable manual evidence source without operational data."""

    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        session.merge(DataSourceRecord(
            id="manual-evidence", name="Manual evidence", type="UPLOAD",
            description="Platform-owned source for uploaded and manually entered evidence",
            url=None, enabled=True, scrape_interval_minutes=None, scraper_type=None,
            scraper_config_json=None, last_run_at=None, next_run_at=None,
            last_status="NEVER", last_error=None, created_at=now, updated_at=now,
        ))


if __name__ == "__main__":
    seed()
