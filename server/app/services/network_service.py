"""Read persisted supply-chain records into domain models."""

from sqlalchemy import select

from app.database import SessionLocal
from app.domain.edge import Edge
from app.domain.network import Network
from app.domain.node import Node
from app.domain.shipment import Shipment
from app.models import EdgeRecord, NodeRecord, ShipmentRecord


def get_network() -> Network:
    """Return the complete persisted network in stable identifier order."""

    with SessionLocal() as session:
        node_records = session.scalars(select(NodeRecord).order_by(NodeRecord.id)).all()
        edge_records = session.scalars(select(EdgeRecord).order_by(EdgeRecord.id)).all()

    return Network(
        nodes=[
            Node(
                id=node.id,
                name=node.name,
                type=node.type,
                inventory=node.inventory,
                capacity=node.capacity,
            )
            for node in node_records
        ],
        edges=[
            Edge(
                id=edge.id,
                source_id=edge.source_id,
                target_id=edge.target_id,
                mode=edge.mode,
                transit_time_hours=edge.transit_time_hours,
                cost=edge.cost,
                capacity=edge.capacity,
            )
            for edge in edge_records
        ],
    )


def get_shipments() -> list[Shipment]:
    """Return all persisted shipments in stable identifier order."""

    with SessionLocal() as session:
        records = session.scalars(
            select(ShipmentRecord).order_by(ShipmentRecord.id)
        ).all()

    return [
        Shipment(
            id=shipment.id,
            origin_id=shipment.origin_id,
            destination_id=shipment.destination_id,
            quantity=shipment.quantity,
            current_node_id=shipment.current_node_id,
            route=shipment.route,
            expected_arrival=shipment.expected_arrival,
        )
        for shipment in records
    ]
