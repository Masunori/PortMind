"""Tests for safe graph, schema, rule, context, and metric extensibility."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain.disruption import CustomFieldEffect, Disruption, DisruptionEffects
from app.domain.edge import Edge
from app.domain.network import Network
from app.domain.network_management import EdgeUpdate, NodeUpdate
from app.domain.node import Node
from app.domain.rule import RuleOperation, RuleTrigger, SimulationRuleCreate
from app.domain.schema import (
    EntityKind,
    FieldBehavior,
    FieldDefinition,
    FieldType,
    SchemaCreate,
    SchemaVersionCreate,
)
from app.domain.shipment import Shipment
from app.models import ShipmentRecord
from app.services.ai_context import build_filter_context, build_interpreter_context
from app.services.context_version_service import get_context_version
from app.services.disruption_service import save_disruption
from app.services.graph_service import (
    create_edge,
    create_node,
    delete_edge,
    delete_node,
    edge_delete_impact,
    node_delete_impact,
    update_edge,
    update_node,
)
from app.services.rule_service import save_rule, validate_rule
from app.services.schema_service import (
    create_schema,
    create_schema_version,
    preview_schema_version,
)
from app.simulation.engine import simulate
from app.simulation.rules import apply_rule


def field(
    key: str = "carbon_kg",
    *,
    field_type: FieldType = FieldType.NUMBER,
    default: object = 0,
    behavior: FieldBehavior = FieldBehavior.FLOW,
) -> FieldDefinition:
    """Build a reusable custom-field definition."""

    return FieldDefinition(
        key=key,
        label=key.replace("_", " ").title(),
        type=field_type,
        required=True,
        default=default,
        unit="kg" if field_type is FieldType.NUMBER else None,
        behavior=behavior,
    )


def schema(kind: EntityKind, fields: list[FieldDefinition] | None = None):
    """Persist a test schema and return its current view."""

    return create_schema(
        SchemaCreate(
            id=f"test-{kind.value.lower()}",
            name=f"Test {kind.value.title()}",
            entity_kind=kind,
            fields=fields or [],
        )
    )


def test_schema_definitions_reject_unsafe_shapes() -> None:
    """Core collisions, bad defaults, and incomplete enums are rejected."""

    with pytest.raises(ValidationError, match="expects INTEGER"):
        field(field_type=FieldType.INTEGER, default=1.5)
    with pytest.raises(ValidationError, match="at least one value"):
        FieldDefinition(key="tier", label="Tier", type=FieldType.ENUM)
    with pytest.raises(ValidationError, match="cannot replace core"):
        SchemaCreate(
            id="bad",
            name="Bad",
            entity_kind=EntityKind.NODE,
            fields=[FieldDefinition(key="capacity", label="Capacity", type=FieldType.NUMBER)],
        )


def test_schema_version_migrates_defaults_and_rejects_destructive_edits(
    test_session_factory,
) -> None:
    """Safe versions migrate entities while destructive changes are refused."""

    current = schema(EntityKind.NODE)
    create_node(Node(id="n1", name="Node", type="port", inventory=0, capacity=10, schema_version_id=current.current_version_id))
    values = SchemaVersionCreate(fields=[field("berth_count", field_type=FieldType.INTEGER, default=1, behavior=FieldBehavior.STATIC)])
    assert preview_schema_version(current.id, values).entity_count == 1
    successor = create_schema_version(current.id, values)
    updated = update_node("n1", NodeUpdate())
    assert successor.version == 2
    assert updated.schema_version_id == successor.current_version_id
    assert updated.attributes == {"berth_count": 1}

    with pytest.raises(ValueError, match="cannot be removed"):
        create_schema_version(current.id, SchemaVersionCreate(fields=[]))
    changed_type = field("berth_count", field_type=FieldType.NUMBER, default=1)
    with pytest.raises(ValueError, match="type cannot change"):
        create_schema_version(current.id, SchemaVersionCreate(fields=[changed_type]))


def test_graph_crud_validates_topology_attributes_and_dependencies(test_session_factory) -> None:
    """Mutations protect IDs, endpoints, typed attributes, and referenced data."""

    node_schema = schema(EntityKind.NODE, [field("berths", field_type=FieldType.INTEGER, default=1, behavior=FieldBehavior.STATIC)])
    edge_schema = schema(EntityKind.EDGE, [field()])
    for identifier in ("a", "b", "c"):
        create_node(Node(id=identifier, name=identifier.upper(), type="port", inventory=0, capacity=100, schema_version_id=node_schema.current_version_id, attributes={"berths": 2}))
    with pytest.raises(ValueError, match="already exists"):
        create_node(Node(id="a", name="Again", type="port", inventory=0, capacity=1))
    with pytest.raises(ValueError, match="Unknown custom fields"):
        update_node("a", NodeUpdate(attributes={"unknown": 2}))

    edge = create_edge(Edge(id="ab", source_id="a", target_id="b", mode="sea", transit_time_hours=5, cost=10, capacity=20, schema_version_id=edge_schema.current_version_id, attributes={"carbon_kg": 4}))
    assert edge.attributes["carbon_kg"] == 4
    with pytest.raises(ValueError, match="different"):
        create_edge(edge.model_copy(update={"id": "loop", "target_id": "a"}))
    with pytest.raises(ValueError, match="must exist"):
        update_edge("ab", EdgeUpdate(target_id="missing"))

    with test_session_factory.begin() as session:
        session.add(ShipmentRecord(id="s1", origin_id="a", destination_id="b", quantity=1, current_node_id="a", route=["a", "b"], expected_arrival=datetime.now(timezone.utc)))
    assert edge_delete_impact("ab").shipment_count == 1
    assert node_delete_impact("a").edge_count == 1
    with pytest.raises(ValueError, match="shipment"):
        delete_edge("ab")
    delete_node("c")
    with pytest.raises(LookupError):
        node_delete_impact("c")


def test_context_version_and_canonical_context_follow_configuration(test_session_factory) -> None:
    """Graph, schema, and rule mutations invalidate authoritative AI context."""

    initial = get_context_version()
    edge_schema = schema(EntityKind.EDGE, [field()])
    create_node(Node(id="a", name="Hai Phong", type="port", inventory=0, capacity=10))
    create_node(Node(id="b", name="Singapore", type="port", inventory=0, capacity=10))
    create_edge(Edge(id="route", source_id="a", target_id="b", mode="sea", transit_time_hours=1, cost=2, capacity=3, schema_version_id=edge_schema.current_version_id, attributes={"carbon_kg": 7}))
    rule = save_rule(SimulationRuleCreate(id="carbon", name="Accumulate carbon", trigger=RuleTrigger.EDGE_TRAVERSED, operation=RuleOperation.ADD, source="edge.attributes.carbon_kg", target_metric="total_carbon_kg"))
    assert get_context_version() >= initial + 5
    assert "Hai Phong" in build_filter_context().text
    detailed = build_interpreter_context("Hai Phong")
    assert "carbon_kg:NUMBER" in detailed.text
    assert "a->b" in detailed.text
    assert rule.id == "carbon"


@pytest.mark.parametrize(
    ("operation", "expected"),
    [(RuleOperation.SET, 3), (RuleOperation.ADD, 5), (RuleOperation.SUBTRACT, -1), (RuleOperation.MULTIPLY, 6), (RuleOperation.MIN, 2), (RuleOperation.MAX, 3)],
)
def test_fixed_rule_operations(operation: RuleOperation, expected: float) -> None:
    """Every permitted numeric operation is deterministic."""

    assert apply_rule(2, 3, operation) == expected


def test_rule_validation_and_custom_metric_end_to_end(test_session_factory) -> None:
    """A typed edge FLOW field safely accumulates into a simulation metric."""

    edge_schema = schema(EntityKind.EDGE, [field()])
    values = SimulationRuleCreate(id="carbon", name="Carbon", trigger=RuleTrigger.EDGE_TRAVERSED, operation=RuleOperation.ADD, source="edge.attributes.carbon_kg", target_metric="total_carbon_kg")
    rule = save_rule(values)
    with pytest.raises(ValueError, match="supports EDGE_TRAVERSED"):
        validate_rule(values.model_copy(update={"trigger": RuleTrigger.NODE_ENTERED}))
    with pytest.raises(ValueError, match="not an available"):
        validate_rule(values.model_copy(update={"source": "edge.attributes.unknown"}))

    network = Network(
        nodes=[Node(id="a", name="A", type="port", inventory=10, capacity=10), Node(id="b", name="B", type="port", inventory=0, capacity=10)],
        edges=[Edge(id="ab", source_id="a", target_id="b", mode="sea", transit_time_hours=2, cost=5, capacity=10, schema_version_id=edge_schema.current_version_id, attributes={"carbon_kg": 4200})],
    )
    shipment = Shipment(id="s", origin_id="a", destination_id="b", quantity=1, current_node_id="a", route=["a", "b"], expected_arrival=datetime.now(timezone.utc))
    result = simulate(network, [shipment], rules=[rule])
    assert result.custom_metrics == {"total_carbon_kg": 4200}

    disruption = Disruption(id="carbon-factor", type="TRANSIT_DELAY", affected_edge_ids=["ab"], start_time=0, end_time=10, effects=DisruptionEffects(custom_effects=[CustomFieldEffect(target_field="edge.attributes.carbon_kg", operation=RuleOperation.MULTIPLY, value=1.5)]))
    changed = simulate(network, [shipment], disruptions=[disruption], rules=[rule])
    assert changed.custom_metrics == {"total_carbon_kg": 6300}


def test_custom_disruption_effects_require_declared_numeric_targets(
    test_session_factory,
) -> None:
    """Persistence rejects invented, nonnumeric, or ungrounded custom effects."""

    edge_schema = schema(EntityKind.EDGE, [field()])
    create_node(Node(id="a", name="A", type="port", inventory=1, capacity=10))
    create_node(Node(id="b", name="B", type="port", inventory=0, capacity=10))
    create_edge(Edge(id="ab", source_id="a", target_id="b", mode="sea", transit_time_hours=1, cost=1, capacity=10, schema_version_id=edge_schema.current_version_id, attributes={"carbon_kg": 2}))
    valid = Disruption(id="factor", type="TRANSIT_DELAY", affected_edge_ids=["ab"], start_time=0, end_time=2, effects=DisruptionEffects(custom_effects=[CustomFieldEffect(target_field="edge.attributes.carbon_kg", operation=RuleOperation.MULTIPLY, value=2)]))
    assert save_disruption(valid).id == "factor"
    with pytest.raises(ValueError, match="not a declared numeric"):
        save_disruption(valid.model_copy(update={"effects": DisruptionEffects(custom_effects=[CustomFieldEffect(target_field="edge.attributes.invented", operation=RuleOperation.ADD, value=1)])}))
