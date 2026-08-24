"""Deterministic execution of validated declarative simulation rules."""

from app.domain.edge import Edge
from app.domain.rule import RuleOperation, SimulationRule
from app.domain.shipment import Shipment


def resolve_source(rule: SimulationRule, edge: Edge, shipment: Shipment) -> float:
    """Resolve a value from the fixed source vocabulary."""

    if rule.source.startswith("edge.attributes."):
        value = edge.attributes.get(rule.source.rsplit(".", 1)[-1])
    elif rule.source.startswith("edge."):
        value = getattr(edge, rule.source.split(".", 1)[1])
    elif rule.source == "shipment.quantity":
        value = shipment.quantity
    else:
        raise ValueError(f"Unsupported rule source {rule.source}")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Rule source {rule.source} is not numeric")
    return float(value)


def apply_rule(current: float, value: float, operation: RuleOperation) -> float:
    """Apply one operation without evaluating arbitrary expressions."""

    return {
        RuleOperation.SET: value,
        RuleOperation.ADD: current + value,
        RuleOperation.SUBTRACT: current - value,
        RuleOperation.MULTIPLY: current * value,
        RuleOperation.MIN: min(current, value),
        RuleOperation.MAX: max(current, value),
    }[operation]


def apply_edge_rules(metrics: dict[str, float], rules: list[SimulationRule], edge: Edge, shipment: Shipment) -> None:
    """Execute enabled EDGE_TRAVERSED rules in stable supplied order."""

    for rule in rules:
        if not rule.enabled or rule.trigger.value != "EDGE_TRAVERSED": continue
        current = metrics.get(rule.target_metric, 1.0 if rule.operation is RuleOperation.MULTIPLY else 0.0)
        metrics[rule.target_metric] = apply_rule(current, resolve_source(rule, edge, shipment), rule.operation)
