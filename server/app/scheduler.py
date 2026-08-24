"""Application-local polling scheduler for independently configured sources."""

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.services.scheduler_service import collect_due_sources


def build_scheduler() -> AsyncIOScheduler:
    """Build a minute-level scheduler without starting it."""

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        collect_due_sources,
        "interval",
        minutes=1,
        id="collect-due-sources",
        max_instances=1,
        coalesce=True,
    )
    return scheduler
