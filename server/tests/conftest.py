"""Shared domain and isolated-database fixtures for backend tests."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.domain.edge import Edge
from app.domain.network import Network
from app.domain.node import Node
from app.domain.shipment import Shipment
from app.services import disruption_service
from app.services import document_service
from app.services import alias_service
from app.services import candidate_service
from app.services import event_service
from app.services import network_service
from app.services import plan_service
from app.services import scenario_service
from app.services import source_service
from app.services import scheduler_service
from app.services import run_service
from app.services import relevance_service
from app.services import context_version_service
from app.services import graph_service
from app.services import rule_service
from app.services import schema_service
from app import seed as seed_module


@pytest.fixture
def sample_network() -> Network:
    """Build a three-node network with a 42-hour route."""

    return Network(
        nodes=[
            Node(
                id="supplier",
                name="Supplier",
                type="supplier",
                inventory=500,
                capacity=1000,
            ),
            Node(
                id="port",
                name="Port",
                type="port",
                inventory=100,
                capacity=2000,
            ),
            Node(
                id="customer",
                name="Customer",
                type="customer",
                inventory=0,
                capacity=500,
            ),
        ],
        edges=[
            Edge(
                id="supplier-port",
                source_id="supplier",
                target_id="port",
                mode="truck",
                transit_time_hours=12,
                cost=400,
                capacity=500,
            ),
            Edge(
                id="port-customer",
                source_id="port",
                target_id="customer",
                mode="sea",
                transit_time_hours=30,
                cost=2400,
                capacity=1000,
            ),
        ],
    )


@pytest.fixture
def sample_shipment() -> Shipment:
    """Build a shipment traversing the complete sample network."""

    return Shipment(
        id="shipment-1",
        origin_id="supplier",
        destination_id="customer",
        quantity=200,
        current_node_id="supplier",
        route=["supplier", "port", "customer"],
        expected_arrival=datetime(2026, 8, 24, tzinfo=timezone.utc),
    )


@pytest.fixture
def test_session_factory(monkeypatch: pytest.MonkeyPatch):
    """Replace application sessions with an isolated in-memory database."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    monkeypatch.setattr(seed_module, "SessionLocal", factory)
    monkeypatch.setattr(disruption_service, "SessionLocal", factory)
    monkeypatch.setattr(document_service, "SessionLocal", factory)
    monkeypatch.setattr(alias_service, "SessionLocal", factory)
    monkeypatch.setattr(candidate_service, "SessionLocal", factory)
    monkeypatch.setattr(event_service, "SessionLocal", factory)
    monkeypatch.setattr(network_service, "SessionLocal", factory)
    monkeypatch.setattr(plan_service, "SessionLocal", factory)
    monkeypatch.setattr(scenario_service, "SessionLocal", factory)
    monkeypatch.setattr(run_service, "SessionLocal", factory)
    monkeypatch.setattr(relevance_service, "SessionLocal", factory)
    monkeypatch.setattr(context_version_service, "SessionLocal", factory)
    monkeypatch.setattr(graph_service, "SessionLocal", factory)
    monkeypatch.setattr(rule_service, "SessionLocal", factory)
    monkeypatch.setattr(schema_service, "SessionLocal", factory)
    monkeypatch.setattr(source_service, "SessionLocal", factory)
    monkeypatch.setattr(scheduler_service, "get_due_sources", source_service.get_due_sources)
    monkeypatch.setattr(scheduler_service, "record_source_run", source_service.record_source_run)

    yield factory

    Base.metadata.drop_all(engine)
    engine.dispose()
