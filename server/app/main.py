"""FastAPI application assembly and system health endpoints."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import asyncio
import logging
import os
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.evidence import router as evidence_router
from app.api.experiment import router as experiment_router
from app.api.plan import router as plan_router
from app.api.planning import router as planning_router
from app.api.prompts import router as prompts_router
from app.api.source import router as source_router
from app.api.scenario import router as scenario_router
from app.api.signal import router as signal_router
from app.integrations import get_client_gateway
from app.integrations.errors import ClientGatewayError
from app.integrations.gateway import ClientGateway
from app.scheduler import build_scheduler, scheduling_enabled
from app.database import engine
from app.repositories import get_storage
from app.repositories.errors import ConflictError, NotFoundError, UnavailableError, ValidationError


logger = logging.getLogger(__name__)

# Validate operator selection while assembling the application. This is intentionally
# fail-closed; runtime storage errors never cause a backend switch.
_configured_storage = get_storage()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Optionally run local source scheduling for this application process."""

    scheduler = None
    if scheduling_enabled():
        scheduler = build_scheduler()
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AEGIS API", lifespan=lifespan)

@app.exception_handler(ConflictError)
async def persistence_conflict(_request, error: ConflictError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=409, content={"detail": str(error)})

@app.exception_handler(NotFoundError)
async def persistence_not_found(_request, error: NotFoundError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": str(error)})

@app.exception_handler(ValidationError)
async def persistence_validation(_request, error: ValidationError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422, content={"detail": str(error)})

@app.exception_handler(UnavailableError)
async def persistence_unavailable(request: Request, error: UnavailableError):
    from fastapi.responses import JSONResponse

    logger.error(
        "Persistence unavailable for %s %s",
        request.method,
        request.url.path,
        exc_info=(type(error), error, error.__traceback__),
    )
    return JSONResponse(status_code=503, content={"detail": "storage unavailable"})
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
app.include_router(prompts_router)
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


@app.get("/health/storage", tags=["system"])
def storage_health() -> dict[str, str]:
    """Report the explicitly selected persistence backend and its health."""

    storage = get_storage()
    try:
        storage.check_health()
    except UnavailableError as error:
        raise HTTPException(status_code=503, detail="storage unavailable") from error
    return {"status": "ok", "storage": "ok", "backend": storage.backend}


@app.get("/health/db", tags=["system"], deprecated=True)
def database_health() -> dict[str, str]:
    """Retained PostgreSQL diagnostic alias for compatibility."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return {"status": "ok", "database": "ok"}


# Lambda uses the fully assembled ASGI application without starting process-local
# services. Lifespan remains active under Uvicorn for explicitly enabled local use.
asyncio.set_event_loop(asyncio.new_event_loop())
_lambda_adapter = Mangum(app, lifespan="off")


def handler(event: dict[str, object], context: object) -> dict[str, object]:
    """Handle a Function URL event, restoring a loop when Python has cleared it."""

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    return _lambda_adapter(event, context)
