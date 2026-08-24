"""Reconstruct the deterministic synthetic supply-chain dataset."""

from datetime import datetime, timezone

from sqlalchemy import delete

from app.database import SessionLocal
from app.models import (
    DisruptionRecord,
    EdgeRecord,
    EntityAliasRecord,
    EntitySchemaRecord,
    NetworkContextStateRecord,
    NodeRecord,
    PlanRecord,
    RunEventRecord,
    RunRecord,
    ScenarioRecord,
    ShipmentRecord,
    SchemaVersionRecord,
    SimulationRuleRecord,
)


NODE_IDS = [
    "supplier-vn",
    "hai-phong-port",
    "psa-singapore",
    "singapore-warehouse",
    "customer",
]


def seed() -> None:
    """Replace all supply-chain records with the baseline synthetic network."""

    now = datetime.now(timezone.utc)
    schema_specs = (
        ("node-supplier", "Supplier", "NODE"),
        ("node-port", "Port", "NODE"),
        ("node-warehouse", "Warehouse", "NODE"),
        ("node-customer", "Customer", "NODE"),
        ("edge-truck", "Truck Route", "EDGE"),
        ("edge-sea", "Sea Route", "EDGE"),
        ("edge-air", "Air Route", "EDGE"),
    )
    schemas = [
        EntitySchemaRecord(
            id=identifier,
            name=name,
            entity_kind=kind,
            current_version_id=f"{identifier}:v1",
            created_at=now,
        )
        for identifier, name, kind in schema_specs
    ]
    schema_versions = [
        SchemaVersionRecord(
            id=f"{identifier}:v1",
            schema_id=identifier,
            version=1,
            fields=[],
            created_at=now,
        )
        for identifier, _name, _kind in schema_specs
    ]
    nodes = [
        NodeRecord(
            id="supplier-vn",
            name="Supplier VN",
            type="supplier",
            inventory=1200,
            capacity=2000,
            schema_version_id="node-supplier:v1",
            attributes={},
        ),
        NodeRecord(
            id="hai-phong-port",
            name="Hai Phong Port",
            type="port",
            inventory=400,
            capacity=6000,
            schema_version_id="node-port:v1",
            attributes={},
        ),
        NodeRecord(
            id="psa-singapore",
            name="PSA Singapore",
            type="port",
            inventory=800,
            capacity=10000,
            schema_version_id="node-port:v1",
            attributes={},
        ),
        NodeRecord(
            id="ho-chi-minh-port",
            name="Ho Chi Minh Port",
            type="port",
            inventory=200,
            capacity=5000,
            schema_version_id="node-port:v1",
            attributes={},
        ),
        NodeRecord(
            id="singapore-warehouse",
            name="Singapore Warehouse",
            type="warehouse",
            inventory=600,
            capacity=3000,
            schema_version_id="node-warehouse:v1",
            attributes={},
        ),
        NodeRecord(
            id="customer",
            name="Customer",
            type="customer",
            inventory=100,
            capacity=1000,
            schema_version_id="node-customer:v1",
            attributes={},
        ),
    ]
    edges = [
        EdgeRecord(
            id="01-supplier-to-hai-phong",
            source_id="supplier-vn",
            target_id="hai-phong-port",
            mode="truck",
            transit_time_hours=4,
            cost=250,
            capacity=800,
            schema_version_id="edge-truck:v1",
            attributes={},
        ),
        EdgeRecord(
            id="02-hai-phong-to-psa",
            source_id="hai-phong-port",
            target_id="psa-singapore",
            mode="sea",
            transit_time_hours=36,
            cost=1800,
            capacity=5000,
            schema_version_id="edge-sea:v1",
            attributes={},
        ),
        EdgeRecord(
            id="03-psa-to-warehouse",
            source_id="psa-singapore",
            target_id="singapore-warehouse",
            mode="truck",
            transit_time_hours=1,
            cost=180,
            capacity=1200,
            schema_version_id="edge-truck:v1",
            attributes={},
        ),
        EdgeRecord(
            id="04-warehouse-to-customer",
            source_id="singapore-warehouse",
            target_id="customer",
            mode="truck",
            transit_time_hours=1,
            cost=90,
            capacity=500,
            schema_version_id="edge-truck:v1",
            attributes={},
        ),
        EdgeRecord(
            id="05-supplier-to-ho-chi-minh",
            source_id="supplier-vn",
            target_id="ho-chi-minh-port",
            mode="truck",
            transit_time_hours=6,
            cost=300,
            capacity=800,
            schema_version_id="edge-truck:v1",
            attributes={},
        ),
        EdgeRecord(
            id="06-ho-chi-minh-to-psa",
            source_id="ho-chi-minh-port",
            target_id="psa-singapore",
            mode="sea",
            transit_time_hours=30,
            cost=2300,
            capacity=4000,
            schema_version_id="edge-sea:v1",
            attributes={},
        ),
        EdgeRecord(
            id="07-supplier-to-psa-air",
            source_id="supplier-vn",
            target_id="psa-singapore",
            mode="air",
            transit_time_hours=8,
            cost=9000,
            capacity=600,
            schema_version_id="edge-air:v1",
            attributes={},
        ),
    ]
    shipments = [
        ShipmentRecord(
            id="shipment-001",
            origin_id="supplier-vn",
            destination_id="customer",
            quantity=300,
            current_node_id="psa-singapore",
            route=NODE_IDS,
            expected_arrival=datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc),
        ),
        ShipmentRecord(
            id="shipment-002",
            origin_id="supplier-vn",
            destination_id="customer",
            quantity=200,
            current_node_id="hai-phong-port",
            route=NODE_IDS,
            expected_arrival=datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc),
        ),
    ]
    scenarios = [
        ScenarioRecord(
            id=f"scenario-{label.lower()}",
            name=f"{duration}h closure",
            probability=probability,
            disruptions=[
                {
                    "id": f"hai-phong-{duration}h-closure",
                    "type": "EDGE_CLOSURE",
                    "enabled": True,
                    "affected_node_ids": [],
                    "affected_edge_ids": ["02-hai-phong-to-psa"],
                    "start_time": 0,
                    "end_time": duration,
                    "effects": {"edge_disabled": True},
                }
            ],
        )
        for label, duration, probability in (
            ("A", 24, 0.45),
            ("B", 48, 0.35),
            ("C", 72, 0.15),
            ("D", 120, 0.05),
        )
    ]
    plans = [
        PlanRecord(
            id="plan-1-wait",
            name="Plan 1 — Wait",
            actions=[{"type": "WAIT"}],
        ),
        PlanRecord(
            id="plan-2-reroute",
            name="Plan 2 — Reroute",
            actions=[
                {
                    "type": "REROUTE_SHIPMENT",
                    "shipment_id": shipment_id,
                    "new_route": [
                        "supplier-vn",
                        "ho-chi-minh-port",
                        "psa-singapore",
                        "singapore-warehouse",
                        "customer",
                    ],
                }
                for shipment_id in ("shipment-001", "shipment-002")
            ],
        ),
        PlanRecord(
            id="plan-3-air-freight",
            name="Plan 3 — Emergency air freight",
            actions=[
                {
                    "type": "EXPEDITE_SHIPMENT",
                    "shipment_id": shipment_id,
                    "new_route": [
                        "supplier-vn",
                        "psa-singapore",
                        "singapore-warehouse",
                        "customer",
                    ],
                }
                for shipment_id in ("shipment-001", "shipment-002")
            ],
        ),
    ]

    with SessionLocal.begin() as session:
        session.execute(delete(RunEventRecord))
        session.execute(delete(RunRecord))
        session.execute(delete(PlanRecord))
        session.execute(delete(ScenarioRecord))
        session.execute(delete(DisruptionRecord))
        session.execute(delete(ShipmentRecord))
        session.execute(delete(EdgeRecord))
        session.execute(delete(NodeRecord))
        session.execute(delete(EntityAliasRecord))
        session.execute(delete(SimulationRuleRecord))
        session.execute(delete(SchemaVersionRecord))
        session.execute(delete(EntitySchemaRecord))
        session.execute(delete(NetworkContextStateRecord))
        session.add_all(schemas)
        session.add_all(schema_versions)
        session.flush()
        session.add_all(nodes)
        session.flush()
        session.add_all(
            [
                EntityAliasRecord(
                    alias=alias,
                    entity_type="NODE",
                    entity_id="hai-phong-port",
                    created_at=datetime.now(timezone.utc),
                )
                for alias in (
                    "hai phong",
                    "hai phong port",
                    "port of hai phong",
                    "vnhph",
                )
            ]
        )
        session.add_all(edges)
        session.add_all(shipments)
        session.add_all(scenarios)
        session.add_all(plans)

    print("Seeded 6 nodes, 7 edges, 2 shipments, 4 scenarios, and 3 plans.")


if __name__ == "__main__":
    seed()
