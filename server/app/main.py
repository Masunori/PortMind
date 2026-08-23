"""FastAPI application assembly and system health endpoints."""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.disruption import router as disruption_router
from app.api.demo import router as demo_router
from app.api.network import router as network_router
from app.api.plan import router as plan_router
from app.api.run import router as run_router
from app.api.scenario import router as scenario_router
from app.api.simulation import router as simulation_router
from app.database import engine

app = FastAPI(title="PSA ESG API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CLIENT_ORIGIN", "http://localhost:3000")],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(demo_router)
app.include_router(disruption_router)
app.include_router(network_router)
app.include_router(plan_router)
app.include_router(run_router)
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
