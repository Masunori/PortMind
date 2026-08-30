"""FastAPI application assembly and system health endpoints."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.evidence import router as evidence_router
from app.api.experiment import router as experiment_router
from app.api.plan import router as plan_router
from app.api.planning import router as planning_router
from app.api.source import router as source_router
from app.api.scenario import router as scenario_router
from app.api.signal import router as signal_router
from app.database import engine
from app.integrations import get_client_gateway
from app.integrations.errors import ClientGatewayError
from app.integrations.gateway import ClientGateway
from app.scheduler import build_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Optionally run local source scheduling for this application process."""

    scheduler = None
    if os.getenv("ENABLE_SOURCE_SCHEDULER", "false").casefold() == "true":
        scheduler = build_scheduler()
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AEGIS API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CLIENT_ORIGIN", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(evidence_router)
app.include_router(experiment_router)
app.include_router(plan_router)
app.include_router(planning_router)
app.include_router(source_router)
app.include_router(scenario_router)
app.include_router(signal_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Report whether the FastAPI process is responsive."""

    return {"status": "ok"}


@app.get("/health/client", tags=["system"])
async def client_health(
    gateway: ClientGateway = Depends(get_client_gateway),
) -> dict[str, str | None]:
    """Report sanitized connectivity and version diagnostics for the client."""

    try:
        context = await gateway.get_context()
    except ClientGatewayError as error:
        return {
            "status": "degraded", "client_id": None, "context_version": None,
            "schema_version": None, "state_version": None,
            "capability_version": None, "last_successful_response_at": None,
            "error_code": error.code,
        }
    return {
        "status": "ok", "client_id": context.client_id,
        "context_version": context.context_version,
        "schema_version": context.schema_version,
        "state_version": context.state_version,
        "capability_version": context.capability_version,
        "last_successful_response_at": datetime.now(timezone.utc).isoformat(),
        "error_code": None,
    }


@app.get("/health/db", tags=["system"])
def database_health() -> dict[str, str]:
    """Report whether the application can execute a PostgreSQL query."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error

    return {"status": "ok", "database": "ok"}
