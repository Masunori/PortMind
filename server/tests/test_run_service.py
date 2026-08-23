"""Tests for persisted observable background orchestration runs."""

import asyncio

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.ai import MockAIProvider
from app.domain.run import RunEventType, RunRequest, RunStatus
from app.seed import seed
from app.services.run_service import (
    get_run,
    get_run_events,
    process_run,
    start_run,
)


DEMO_SIGNAL = "Severe weather may close Hai Phong for 2–3 days."


def test_observable_run_persists_output_and_all_progress_events(
    test_session_factory: sessionmaker[Session],
) -> None:
    """A background run persists its matrix, ranking, and ordered milestones."""

    seed()
    generated = start_run(RunRequest(signal=DEMO_SIGNAL))

    assert generated.status is RunStatus.GENERATED
    asyncio.run(process_run(generated.run_id, MockAIProvider()))

    completed = get_run(generated.run_id)
    assert completed is not None
    assert completed.status is RunStatus.COMPLETED
    assert len(completed.scenarios) == 4
    assert len(completed.plans) == 4
    assert len(completed.results) == 16
    assert completed.recommendation is not None
    assert "partial-air-sea" in completed.recommendation.recommended_plan
    recommended = next(
        plan for plan in completed.plans
        if plan.id == completed.recommendation.recommended_plan
    )
    assert recommended.status.value == "RECOMMENDED"

    events = get_run_events(generated.run_id)
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    event_types = [event.type for event in events]
    assert event_types[:7] == [
        RunEventType.RUN_STARTED,
        RunEventType.SIGNAL_INTERPRETED,
        RunEventType.ENTITIES_GROUNDED,
        RunEventType.EXPOSURE_ANALYZED,
        RunEventType.SCENARIOS_GENERATED,
        RunEventType.PLANS_GENERATED,
        RunEventType.SIMULATION_STARTED,
    ]
    assert event_types.count(RunEventType.SIMULATION_COMPLETED) == 16
    assert event_types[-2:] == [
        RunEventType.RANKING_COMPLETED,
        RunEventType.RUN_COMPLETED,
    ]
    last_simulation = [
        event for event in events
        if event.type is RunEventType.SIMULATION_COMPLETED
    ][-1]
    assert last_simulation.payload["completed"] == 16
    assert last_simulation.payload["total"] == 16


def test_event_cursor_returns_only_newer_events(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Event polling can resume after an observed sequence number."""

    seed()
    generated = start_run(RunRequest(signal=DEMO_SIGNAL))

    assert get_run_events(generated.run_id, after_sequence=1) == []


def test_failed_run_persists_failure_status_and_event(
    test_session_factory: sessionmaker[Session],
) -> None:
    """Provider failures remain observable and do not leave runs active."""

    seed()
    generated = start_run(RunRequest(signal=DEMO_SIGNAL))
    provider = MockAIProvider(fixtures={}, prompt_fixtures={})

    with pytest.raises(ValueError, match="no fixture"):
        asyncio.run(process_run(generated.run_id, provider))

    failed = get_run(generated.run_id)
    assert failed is not None
    assert failed.status is RunStatus.FAILED
    assert "no fixture" in (failed.error or "")
    assert get_run_events(generated.run_id)[-1].type is RunEventType.RUN_FAILED
