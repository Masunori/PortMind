"""Tests for provider-neutral LangGraph workflow orchestration."""

import asyncio

from sqlalchemy.orm import Session, sessionmaker

from app.agents.orchestrator import build_orchestrator
from app.ai import MockAIProvider
from app.domain.run import RunRequest
from app.seed import seed
from app.services.run_service import execute_run


DEMO_SIGNAL = "Severe weather may close Hai Phong for 2–3 days."


def test_langgraph_executes_complete_local_workflow(
    test_session_factory: sessionmaker[Session],
) -> None:
    """The demo signal reaches interpretation, simulation, and ranking locally."""

    seed()
    graph = build_orchestrator(MockAIProvider())

    state = asyncio.run(graph.ainvoke({"raw_signal": DEMO_SIGNAL}))

    assert state["interpreted_signal"].event_type == "WEATHER_DISRUPTION"
    assert state["grounded_signal"].node_ids == ["hai-phong-port"]
    assert state["disruption"].affected_edge_ids == ["02-hai-phong-to-psa"]
    assert len(state["exposure"].affected_shipments) == 2
    assert len(state["scenarios"]) == 4
    assert len(state["plans"]) == 4
    assert len(state["results"]) == 16
    assert state["ranking"] is not None


def test_langgraph_ends_early_for_unresolved_signal(
    test_session_factory: sessionmaker[Session],
) -> None:
    """A signal without grounded impact stops before generation."""

    seed()
    graph = build_orchestrator(MockAIProvider())

    state = asyncio.run(graph.ainvoke({"raw_signal": "Unknown remote event"}))

    assert state["grounded_signal"].node_ids == []
    assert state["disruption"] is None
    assert state["exposure"] is None
    assert state.get("scenarios", []) == []
    assert state.get("plans", []) == []
    assert state.get("ranking") is None


def test_run_service_returns_synchronous_public_contract(
    test_session_factory: sessionmaker[Session],
) -> None:
    """The initial run service returns an ID and completed workflow payload."""

    seed()

    response = asyncio.run(
        execute_run(RunRequest(signal=DEMO_SIGNAL), MockAIProvider())
    )

    assert response.run_id
    assert response.status.value == "COMPLETED"
    assert len(response.scenarios) == 4
    assert len(response.plans) == 4
    assert len(response.results) == 16
    assert response.recommendation is not None
