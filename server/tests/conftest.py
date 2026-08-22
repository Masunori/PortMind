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
from app.services import network_service
from app.services import plan_service
from app.services import scenario_service
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
    monkeypatch.setattr(network_service, "SessionLocal", factory)
    monkeypatch.setattr(plan_service, "SessionLocal", factory)
    monkeypatch.setattr(scenario_service, "SessionLocal", factory)

    yield factory

    Base.metadata.drop_all(engine)
    engine.dispose()
