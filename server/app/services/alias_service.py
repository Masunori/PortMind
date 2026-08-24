"""Deterministically resolve aliases to authoritative graph entities."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models import EntityAliasRecord
from app.services.entity_resolution import _normalize_name, find_nodes_by_name
from app.services.network_service import get_network
from app.services.context_version_service import bump_context_version


def save_alias(alias: str, entity_type: str, entity_id: str) -> None:
    """Persist a normalized alias after confirming its target exists."""

    network = get_network()
    if entity_type != "NODE" or entity_id not in {node.id for node in network.nodes}:
        raise ValueError("Alias target does not exist")
    with SessionLocal.begin() as session:
        session.merge(
            EntityAliasRecord(
                alias=_normalize_name(alias),
                entity_type=entity_type,
                entity_id=entity_id,
                created_at=datetime.now(timezone.utc),
            )
        )
        bump_context_version(session)


def resolve_node_ids(locations: list[str]) -> tuple[list[str], list[str]]:
    """Resolve aliases or canonical names and return IDs plus unresolved values."""

    network = get_network()
    resolved: set[str] = set()
    unresolved: list[str] = []
    with SessionLocal() as session:
        for location in locations:
            alias = session.get(EntityAliasRecord, _normalize_name(location))
            if alias is not None and alias.entity_type == "NODE":
                resolved.add(alias.entity_id)
                continue
            matches = find_nodes_by_name(location, network)
            if matches:
                resolved.update(node.id for node in matches)
            else:
                unresolved.append(location)
    return sorted(resolved), unresolved


def get_aliases() -> dict[str, str]:
    """Return normalized aliases mapped to authoritative node identifiers."""

    with SessionLocal() as session:
        records = session.scalars(
            select(EntityAliasRecord).order_by(EntityAliasRecord.alias)
        ).all()
    return {record.alias: record.entity_id for record in records}


def seed_default_aliases() -> None:
    """Create common Hai Phong aliases when the canonical node exists."""

    for alias in ("Hai Phong", "Hai Phong Port", "Port of Hai Phong", "VNHPH"):
        save_alias(alias, "NODE", "hai-phong-port")
