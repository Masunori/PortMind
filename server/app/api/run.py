"""HTTP endpoints for observable provider-neutral response runs."""

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from app.domain.run import RunRequest, RunResponse
from app.services.run_service import (
    get_run,
    get_run_events,
    process_run,
    start_run,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=RunResponse)
async def create_run(
    request: RunRequest,
    background_tasks: BackgroundTasks,
) -> RunResponse:
    """Create a run and schedule its local background workflow."""

    response = start_run(request)
    background_tasks.add_task(process_run, response.run_id)
    return response


@router.get("/{run_id}", response_model=RunResponse)
def run(run_id: str) -> RunResponse:
    """Return the latest persisted state for an observable run."""

    response = get_run(run_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return response


@router.get("/{run_id}/events")
def run_events(run_id: str) -> StreamingResponse:
    """Stream persisted workflow events using server-sent events."""

    if get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def stream():
        """Yield ordered events until the run reaches a terminal state."""

        cursor = 0
        while True:
            for event in get_run_events(run_id, cursor):
                cursor = event.sequence
                yield (
                    f"id: {event.sequence}\n"
                    f"event: {event.type.value}\n"
                    f"data: {json.dumps(event.model_dump(mode='json'))}\n\n"
                )
            current = get_run(run_id)
            if current is None or current.status.value in {"COMPLETED", "FAILED"}:
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream")
