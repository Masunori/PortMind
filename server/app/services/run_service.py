"""Persist and execute observable provider-neutral response workflows."""

from datetime import datetime, timezone
from sqlalchemy import func, select
from uuid import uuid4

from app.agents.orchestrator import build_orchestrator
from app.ai import AIProvider, get_ai_provider
from app.database import SessionLocal
from app.domain.plan import Plan, PlanScenarioResult, PlanStatus
from app.domain.ranking import PlanRankingResult
from app.domain.run import (
    RunEvent,
    RunEventType,
    RunRequest,
    RunResponse,
    RunStatus,
)
from app.domain.scenario import Scenario
from app.models import RunEventRecord, RunRecord
from app.services.plan_service import save_plan


def _to_response(record: RunRecord) -> RunResponse:
    """Convert one persisted run record into its public contract."""

    return RunResponse(
        run_id=record.id,
        status=RunStatus(record.status),
        signal=record.signal,
        scenarios=[Scenario.model_validate(item) for item in record.scenarios],
        plans=[Plan.model_validate(item) for item in record.plans],
        results=[PlanScenarioResult.model_validate(item) for item in record.results],
        recommendation=(
            PlanRankingResult.model_validate(record.recommendation)
            if record.recommendation is not None
            else None
        ),
        error=record.error,
    )


def append_run_event(
    run_id: str,
    event_type: RunEventType,
    payload: dict[str, object] | None = None,
) -> RunEvent:
    """Append one monotonically sequenced observable event to a run."""

    now = datetime.now(timezone.utc)
    with SessionLocal.begin() as session:
        maximum = session.scalar(
            select(func.max(RunEventRecord.sequence)).where(
                RunEventRecord.run_id == run_id
            )
        )
        record = RunEventRecord(
            run_id=run_id,
            sequence=(maximum or 0) + 1,
            type=event_type.value,
            payload=payload or {},
            created_at=now,
        )
        session.add(record)
    return RunEvent(
        sequence=record.sequence,
        type=event_type,
        payload=record.payload,
        created_at=record.created_at,
    )


def start_run(request: RunRequest) -> RunResponse:
    """Persist a generated run ready for background execution."""

    now = datetime.now(timezone.utc)
    record = RunRecord(
        id=str(uuid4()),
        signal=request.signal,
        status=RunStatus.GENERATED.value,
        scenarios=[],
        plans=[],
        results=[],
        recommendation=None,
        error=None,
        created_at=now,
        updated_at=now,
    )
    with SessionLocal.begin() as session:
        session.add(record)
    append_run_event(record.id, RunEventType.RUN_STARTED)
    return _to_response(record)


def get_run(run_id: str) -> RunResponse | None:
    """Return one persisted observable run by identifier."""

    with SessionLocal() as session:
        record = session.get(RunRecord, run_id)
        return _to_response(record) if record is not None else None


def get_run_events(run_id: str, after_sequence: int = 0) -> list[RunEvent]:
    """Return ordered persisted events after an optional sequence cursor."""

    with SessionLocal() as session:
        records = session.scalars(
            select(RunEventRecord)
            .where(
                RunEventRecord.run_id == run_id,
                RunEventRecord.sequence > after_sequence,
            )
            .order_by(RunEventRecord.sequence)
        ).all()
    return [
        RunEvent(
            sequence=record.sequence,
            type=RunEventType(record.type),
            payload=record.payload,
            created_at=record.created_at,
        )
        for record in records
    ]


async def process_run(
    run_id: str,
    provider: AIProvider | None = None,
) -> None:
    """Execute a generated run and persist progress, output, or failure."""

    current = get_run(run_id)
    if current is None:
        raise ValueError(f"Unknown run {run_id}")
    with SessionLocal.begin() as session:
        record = session.get(RunRecord, run_id)
        if record is None:
            raise ValueError(f"Unknown run {run_id}")
        record.status = RunStatus.RUNNING.value
        record.updated_at = datetime.now(timezone.utc)

    try:
        graph = build_orchestrator(
            provider or get_ai_provider(),
            lambda event_type, payload: append_run_event(
                run_id,
                event_type,
                payload,
            ),
        )
        state = await graph.ainvoke({"raw_signal": current.signal})
        ranking = state.get("ranking")
        persisted_plans = [
            save_plan(
                plan.model_copy(
                    update={
                        "status": (
                            PlanStatus.RECOMMENDED
                            if ranking is not None
                            and plan.id == ranking.recommended_plan
                            else PlanStatus.GENERATED
                        )
                    }
                )
            )
            for plan in state.get("plans", [])
        ]
        with SessionLocal.begin() as session:
            record = session.get(RunRecord, run_id)
            if record is None:
                raise ValueError(f"Unknown run {run_id}")
            record.status = RunStatus.COMPLETED.value
            record.scenarios = [
                item.model_dump(mode="json") for item in state.get("scenarios", [])
            ]
            record.plans = [
                item.model_dump(mode="json") for item in persisted_plans
            ]
            record.results = [
                item.model_dump(mode="json") for item in state.get("results", [])
            ]
            record.recommendation = (
                ranking.model_dump(mode="json") if ranking is not None else None
            )
            record.updated_at = datetime.now(timezone.utc)
        append_run_event(run_id, RunEventType.RUN_COMPLETED)
    except Exception as error:
        with SessionLocal.begin() as session:
            record = session.get(RunRecord, run_id)
            if record is not None:
                record.status = RunStatus.FAILED.value
                record.error = str(error)
                record.updated_at = datetime.now(timezone.utc)
        append_run_event(run_id, RunEventType.RUN_FAILED, {"error": str(error)})
        raise


async def execute_run(
    request: RunRequest,
    provider: AIProvider | None = None,
) -> RunResponse:
    """Execute one complete local workflow synchronously from the API's view."""

    graph = build_orchestrator(provider or get_ai_provider())
    state = await graph.ainvoke({"raw_signal": request.signal})
    return RunResponse(
        run_id=str(uuid4()),
        status=RunStatus.COMPLETED,
        signal=request.signal,
        scenarios=state.get("scenarios", []),
        plans=state.get("plans", []),
        results=state.get("results", []),
        recommendation=state.get("ranking"),
    )
