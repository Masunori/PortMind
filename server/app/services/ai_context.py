"""Canonical versioned AI context derived only from authoritative persistence."""

from pydantic import BaseModel

from app.domain.disruption import DisruptionType
from app.services.context_version_service import get_context_version
from app.services.network_service import get_network, get_shipments
from app.services.schema_service import get_schemas
from app.services.alias_service import get_aliases


class AIContext(BaseModel):
    """Expose a context version and deterministic text representation."""

    version: int
    text: str


def build_filter_context() -> AIContext:
    """Build compact network context for document classification."""

    network = get_network()
    schemas = get_schemas()
    nodes = "\n".join(f"- {item.name} [{item.type}]" for item in network.nodes)
    routes = "\n".join(f"- {item.source_id}->{item.target_id} [{item.mode}]" for item in network.edges)
    fields = sorted({field.key for schema in schemas for field in schema.fields})
    return AIContext(version=get_context_version(), text=f"Nodes:\n{nodes}\nRoutes:\n{routes}\nCustom operational fields: {', '.join(fields) or 'none'}")


def build_interpreter_context(query: str | None = None) -> AIContext:
    """Build detailed context, retrieving a matching graph subset when requested."""

    network = get_network()
    normalized = (query or "").casefold()
    selected_nodes = [node for node in network.nodes if not normalized or any(token in node.name.casefold() for token in normalized.split() if len(token) > 2)]
    if query and not selected_nodes:
        selected_nodes = network.nodes[:10]
    node_ids = {node.id for node in selected_nodes}
    edges = [edge for edge in network.edges if not query or edge.source_id in node_ids or edge.target_id in node_ids]
    schemas = get_schemas()
    aliases = get_aliases()
    schema_text = "; ".join(f"{schema.id} v{schema.version}: " + ", ".join(f"{field.key}:{field.type.value}" for field in schema.fields) for schema in schemas)
    text = (
        "Authoritative nodes: " + ", ".join(f"{node.name} ({node.id})" for node in selected_nodes)
        + "\nAuthoritative edges: " + ", ".join(f"{edge.id}:{edge.source_id}->{edge.target_id}" for edge in edges)
        + f"\nSchemas: {schema_text or 'none'}"
        + "\nAliases: " + ", ".join(f"{alias}->{identifier}" for alias, identifier in aliases.items())
        + "\nSupported disruption types: " + ", ".join(item.value for item in DisruptionType)
        + "\nSupported custom effects: numeric node.attributes.* or edge.attributes.* using SET, ADD, SUBTRACT, MULTIPLY, MIN, MAX"
    )
    return AIContext(version=get_context_version(), text=text)
