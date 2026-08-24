"""Validated CRUD for the persisted live digital twin."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.domain.edge import Edge
from app.domain.network_management import ChangeImpact, EdgeUpdate, NodeUpdate
from app.domain.node import Node
from app.models import (
    DisruptionCandidateRecord,
    DisruptionRecord,
    EdgeRecord,
    EntityAliasRecord,
    NodeRecord,
    ShipmentRecord,
)
from app.services.context_version_service import bump_context_version
from app.services.schema_service import validate_entity_attributes


def _node(record: NodeRecord) -> Node:
    return Node(id=record.id, name=record.name, type=record.type, inventory=record.inventory, capacity=record.capacity, schema_version_id=record.schema_version_id, attributes=record.attributes or {})


def _edge(record: EdgeRecord) -> Edge:
    return Edge(id=record.id, source_id=record.source_id, target_id=record.target_id, mode=record.mode, transit_time_hours=record.transit_time_hours, cost=record.cost, capacity=record.capacity, schema_version_id=record.schema_version_id, attributes=record.attributes or {})


def create_node(node: Node) -> Node:
    """Create a uniquely identified, schema-valid node."""

    validate_entity_attributes("NODE", node.schema_version_id, node.attributes)
    with SessionLocal.begin() as session:
        if session.get(NodeRecord, node.id):
            raise ValueError("Node ID already exists")
        record = NodeRecord(**node.model_dump())
        session.add(record)
        bump_context_version(session)
    return _node(record)


def update_node(node_id: str, values: NodeUpdate) -> Node:
    """Update mutable node fields after schema validation."""

    with SessionLocal.begin() as session:
        record = session.get(NodeRecord, node_id)
        if record is None:
            raise LookupError("Node not found")
        merged = {"schema_version_id": record.schema_version_id, "attributes": record.attributes or {}, **values.model_dump(exclude_unset=True)}
        validate_entity_attributes("NODE", merged["schema_version_id"], merged["attributes"])
        for key, value in values.model_dump(exclude_unset=True).items():
            setattr(record, key, value)
        bump_context_version(session)
    return _node(record)


def node_delete_impact(node_id: str) -> ChangeImpact:
    """Find every record that prevents safe node deletion."""

    with SessionLocal() as session:
        if session.get(NodeRecord, node_id) is None:
            raise LookupError("Node not found")
        edges = session.scalars(select(EdgeRecord).where((EdgeRecord.source_id == node_id) | (EdgeRecord.target_id == node_id))).all()
        shipments = [item for item in session.scalars(select(ShipmentRecord)).all() if node_id in item.route or node_id in {item.origin_id, item.destination_id, item.current_node_id}]
        disruptions = [item for item in session.scalars(select(DisruptionRecord)).all() if node_id in item.affected_node_ids]
        candidates = [item for item in session.scalars(select(DisruptionCandidateRecord)).all() if node_id in item.affected_node_ids]
        aliases = session.scalars(select(EntityAliasRecord).where(EntityAliasRecord.entity_id == node_id)).all()
    blockers = []
    if edges: blockers.append("Node is referenced by edges")
    if shipments: blockers.append("Node is referenced by shipments")
    if disruptions or candidates: blockers.append("Node is referenced by disruption evidence")
    if aliases: blockers.append("Node is referenced by aliases")
    return ChangeImpact(entity_count=1, edge_count=len(edges), shipment_count=len(shipments), disruption_count=len(disruptions) + len(candidates), alias_count=len(aliases), blockers=blockers)


def delete_node(node_id: str) -> None:
    """Delete an unreferenced node or return all dependency blockers."""

    impact = node_delete_impact(node_id)
    if impact.blockers:
        raise ValueError("; ".join(impact.blockers))
    with SessionLocal.begin() as session:
        session.delete(session.get(NodeRecord, node_id))
        bump_context_version(session)


def create_edge(edge: Edge) -> Edge:
    """Create a directed edge whose distinct endpoints exist."""

    if edge.source_id == edge.target_id:
        raise ValueError("Edge endpoints must be different")
    validate_entity_attributes("EDGE", edge.schema_version_id, edge.attributes)
    with SessionLocal.begin() as session:
        if session.get(EdgeRecord, edge.id): raise ValueError("Edge ID already exists")
        if not session.get(NodeRecord, edge.source_id) or not session.get(NodeRecord, edge.target_id): raise ValueError("Edge endpoints must exist")
        record = EdgeRecord(**edge.model_dump())
        session.add(record)
        bump_context_version(session)
    return _edge(record)


def update_edge(edge_id: str, values: EdgeUpdate) -> Edge:
    """Update an edge while preserving valid topology and schema data."""

    with SessionLocal.begin() as session:
        record = session.get(EdgeRecord, edge_id)
        if record is None: raise LookupError("Edge not found")
        changes = values.model_dump(exclude_unset=True)
        source = changes.get("source_id", record.source_id)
        target = changes.get("target_id", record.target_id)
        if source == target: raise ValueError("Edge endpoints must be different")
        if not session.get(NodeRecord, source) or not session.get(NodeRecord, target): raise ValueError("Edge endpoints must exist")
        validate_entity_attributes("EDGE", changes.get("schema_version_id", record.schema_version_id), changes.get("attributes", record.attributes or {}))
        for key, value in changes.items(): setattr(record, key, value)
        bump_context_version(session)
    return _edge(record)


def edge_delete_impact(edge_id: str) -> ChangeImpact:
    """Find shipments and disruptions preventing edge deletion."""

    with SessionLocal() as session:
        edge = session.get(EdgeRecord, edge_id)
        if edge is None: raise LookupError("Edge not found")
        shipments = [item for item in session.scalars(select(ShipmentRecord)).all() if (edge.source_id, edge.target_id) in set(zip(item.route, item.route[1:]))]
        disruptions = [item for item in session.scalars(select(DisruptionRecord)).all() if edge_id in item.affected_edge_ids]
        candidates = [item for item in session.scalars(select(DisruptionCandidateRecord)).all() if edge_id in item.affected_edge_ids]
    blockers = (["Edge is used by shipment routes"] if shipments else []) + (["Edge is referenced by disruption evidence"] if disruptions or candidates else [])
    return ChangeImpact(entity_count=1, shipment_count=len(shipments), disruption_count=len(disruptions) + len(candidates), blockers=blockers)


def delete_edge(edge_id: str) -> None:
    """Delete an unused edge."""

    impact = edge_delete_impact(edge_id)
    if impact.blockers: raise ValueError("; ".join(impact.blockers))
    with SessionLocal.begin() as session:
        session.delete(session.get(EdgeRecord, edge_id))
        bump_context_version(session)
