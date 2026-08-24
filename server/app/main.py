"""FastAPI application assembly and system health endpoints."""

from contextlib import asynccontextmanager
import os
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.disruption import router as disruption_router
from app.api.assessment import router as assessment_router
from app.api.candidate import router as candidate_router
from app.api.graph import router as graph_router
from app.api.schema import router as schema_router
from app.api.rule import router as rule_router
from app.api.demo import router as demo_router
from app.api.document import router as document_router
from app.api.network import router as network_router
from app.api.plan import router as plan_router
from app.api.run import router as run_router
from app.api.source import router as source_router
from app.api.scenario import router as scenario_router
from app.api.simulation import router as simulation_router
from app.database import engine
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


app = FastAPI(title="PSA ESG API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CLIENT_ORIGIN", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(demo_router)
app.include_router(assessment_router)
app.include_router(candidate_router)
app.include_router(graph_router)
app.include_router(schema_router)
app.include_router(rule_router)
app.include_router(disruption_router)
app.include_router(document_router)
app.include_router(network_router)
app.include_router(plan_router)
app.include_router(run_router)
app.include_router(source_router)
app.include_router(scenario_router)
app.include_router(simulation_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Report whether the FastAPI process is responsive."""

    return {"status": "ok"}


@app.get("/health/db", tags=["system"])
def database_health() -> dict[str, str]:
    """Report whether the application can execute a PostgreSQL query."""

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error

    return {"status": "ok", "database": "ok"}
