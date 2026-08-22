"""Heap-based deterministic supply-chain simulation engine."""

import heapq
from itertools import count

from app.domain.disruption import Disruption
from app.domain.edge import Edge
from app.domain.network import Network
from app.domain.plan import PlanAction, PlanActionType
from app.domain.scenario import Scenario
from app.domain.shipment import Shipment
from app.simulation.events import EventType, SimulationEvent
from app.simulation.result import SimulationResult
from app.simulation.state import SimulationState


def _edge_index(network: Network) -> dict[tuple[str, str], Edge]:
    """Index directed edges by their source and target node identifiers."""

    return {
        (edge.source_id, edge.target_id): edge
        for edge in network.edges
    }


def _validate_shipment(
    shipment: Shipment,
    edges: dict[tuple[str, str], Edge],
    node_ids: set[str],
) -> None:
    """Reject shipments whose route cannot be traversed through the network."""

    if len(shipment.route) < 2:
        raise ValueError(f"Shipment {shipment.id} must have at least two route nodes")
    if shipment.route[0] != shipment.origin_id:
        raise ValueError(f"Shipment {shipment.id} route must start at its origin")
    if shipment.route[-1] != shipment.destination_id:
        raise ValueError(f"Shipment {shipment.id} route must end at its destination")
    unknown_nodes = set(shipment.route) - node_ids
    if unknown_nodes:
        raise ValueError(
            f"Shipment {shipment.id} route has unknown nodes: "
            f"{', '.join(sorted(unknown_nodes))}"
        )

    for source_id, target_id in zip(shipment.route, shipment.route[1:]):
        if (source_id, target_id) not in edges:
            raise ValueError(
                f"Shipment {shipment.id} route has no edge from "
                f"{source_id} to {target_id}"
            )


def _active_disruptions(
    disruptions: list[Disruption],
    time_hours: float,
) -> list[Disruption]:
    """Return disruptions active at the supplied simulation timestamp."""

    return [
        disruption
        for disruption in disruptions
        if disruption.enabled
        and disruption.start_time <= time_hours < disruption.end_time
    ]


def _departure_effects(
    edge: Edge,
    shipment: Shipment,
    time_hours: float,
    node_capacities: dict[str, float],
    disruptions: list[Disruption],
) -> tuple[float | None, float]:
    """Return an optional wait time and adjusted transit duration."""

    transit_time = edge.transit_time_hours
    wait_until: list[float] = []

    for disruption in _active_disruptions(disruptions, time_hours):
        affects_edge = edge.id in disruption.affected_edge_ids
        affects_source = edge.source_id in disruption.affected_node_ids
        affects_target = edge.target_id in disruption.affected_node_ids
        effects = disruption.effects

        if effects.edge_disabled and (affects_edge or affects_source):
            wait_until.append(disruption.end_time)

        if effects.capacity_multiplier is not None:
            if (
                affects_edge
                and shipment.quantity > edge.capacity * effects.capacity_multiplier
            ):
                wait_until.append(disruption.end_time)
            if affects_source or affects_target:
                node_id = edge.source_id if affects_source else edge.target_id
                if (
                    shipment.quantity
                    > node_capacities[node_id] * effects.capacity_multiplier
                ):
                    wait_until.append(disruption.end_time)

        if affects_edge and effects.transit_time_multiplier is not None:
            transit_time *= effects.transit_time_multiplier
        if affects_source:
            if effects.handling_time_multiplier is not None:
                transit_time *= effects.handling_time_multiplier
            if effects.node_handling_delay_hours is not None:
                transit_time += effects.node_handling_delay_hours

    return (max(wait_until) if wait_until else None), transit_time


def _apply_actions(
    shipments: list[Shipment],
    actions: list[PlanAction],
) -> tuple[list[Shipment], dict[str, tuple[float, float]]]:
    """Return action-adjusted shipments and per-shipment time/cost modifiers."""

    adjusted = {shipment.id: shipment.model_copy(deep=True) for shipment in shipments}
    modifiers: dict[str, tuple[float, float]] = {}

    for action in actions:
        if action.type is PlanActionType.WAIT:
            continue
        if action.shipment_id not in adjusted:
            raise ValueError(f"Action references unknown shipment {action.shipment_id}")

        shipment = adjusted[action.shipment_id]
        if action.new_route is not None:
            shipment = shipment.model_copy(update={"route": action.new_route})
        if action.type is PlanActionType.USE_ALTERNATIVE_INVENTORY:
            shipment = shipment.model_copy(
                update={
                    "origin_id": action.alternative_inventory_node_id,
                    "current_node_id": action.alternative_inventory_node_id,
                }
            )
        adjusted[action.shipment_id] = shipment

        if action.type is PlanActionType.EXPEDITE_SHIPMENT:
            current_time, current_cost = modifiers.get(action.shipment_id, (1, 1))
            modifiers[action.shipment_id] = (
                current_time * action.transit_time_multiplier,
                current_cost * action.cost_multiplier,
            )

    return list(adjusted.values()), modifiers


def simulate(
    network: Network,
    shipments: list[Shipment],
    horizon_hours: float = 168,
    disruptions: list[Disruption] | None = None,
    actions: list[PlanAction] | None = None,
    scenario: Scenario | None = None,
) -> SimulationResult:
    """Simulate shipment traversal and active disruption effects."""

    if horizon_hours <= 0:
        raise ValueError("Simulation horizon must be greater than zero")
    if len({shipment.id for shipment in shipments}) != len(shipments):
        raise ValueError("Shipment IDs must be unique")
    if scenario is not None and disruptions is not None:
        raise ValueError("Supply either scenario or disruptions, not both")

    shipments, action_modifiers = _apply_actions(shipments, actions or [])
    edges = _edge_index(network)
    node_ids = {node.id for node in network.nodes}
    node_capacities = {node.id: node.capacity for node in network.nodes}
    disruptions = scenario.disruptions if scenario is not None else disruptions or []
    shipments_by_id = {shipment.id: shipment for shipment in shipments}

    state = SimulationState(
        inventory={node.id: node.inventory for node in network.nodes},
        shipment_locations={
            shipment.id: shipment.origin_id
            for shipment in shipments
        },
    )
    queue: list[SimulationEvent] = []
    sequence = count()
    planned_lead_times: dict[str, float] = {}

    for shipment in shipments:
        _validate_shipment(shipment, edges, node_ids)
        time_multiplier, _ = action_modifiers.get(shipment.id, (1, 1))
        planned_lead_times[shipment.id] = sum(
            edges[(source_id, target_id)].transit_time_hours
            for source_id, target_id in zip(shipment.route, shipment.route[1:])
        ) * time_multiplier
        origin_inventory = state.inventory.get(shipment.origin_id)
        if origin_inventory is None:
            raise ValueError(f"Shipment {shipment.id} has an unknown origin")
        if origin_inventory < shipment.quantity:
            raise ValueError(f"Shipment {shipment.id} exceeds origin inventory")

        state.inventory[shipment.origin_id] -= shipment.quantity
        heapq.heappush(
            queue,
            SimulationEvent(
                time_hours=0,
                sequence=next(sequence),
                shipment_id=shipment.id,
                event_type=EventType.DEPARTURE,
                route_index=0,
            ),
        )

    while queue:
        event = heapq.heappop(queue)
        if event.time_hours > horizon_hours:
            state.late_shipments.add(event.shipment_id)
            continue

        state.current_time_hours = event.time_hours
        shipment = shipments_by_id[event.shipment_id]

        if event.event_type is EventType.DEPARTURE:
            source_id = shipment.route[event.route_index]
            target_id = shipment.route[event.route_index + 1]
            edge = edges[(source_id, target_id)]
            wait_until, transit_time = _departure_effects(
                edge=edge,
                shipment=shipment,
                time_hours=event.time_hours,
                node_capacities=node_capacities,
                disruptions=disruptions,
            )
            if wait_until is not None:
                heapq.heappush(
                    queue,
                    SimulationEvent(
                        time_hours=wait_until,
                        sequence=next(sequence),
                        shipment_id=shipment.id,
                        event_type=EventType.DEPARTURE,
                        route_index=event.route_index,
                    ),
                )
                continue

            time_multiplier, cost_multiplier = action_modifiers.get(
                shipment.id,
                (1, 1),
            )
            transit_time *= time_multiplier
            state.total_cost += edge.cost * cost_multiplier
            heapq.heappush(
                queue,
                SimulationEvent(
                    time_hours=event.time_hours + transit_time,
                    sequence=next(sequence),
                    shipment_id=shipment.id,
                    event_type=EventType.ARRIVAL,
                    route_index=event.route_index + 1,
                ),
            )
            continue

        current_node_id = shipment.route[event.route_index]
        state.shipment_locations[shipment.id] = current_node_id

        if event.route_index == len(shipment.route) - 1:
            state.inventory[current_node_id] += shipment.quantity
            state.lead_times[shipment.id] = event.time_hours
        else:
            heapq.heappush(
                queue,
                SimulationEvent(
                    time_hours=event.time_hours,
                    sequence=next(sequence),
                    shipment_id=shipment.id,
                    event_type=EventType.DEPARTURE,
                    route_index=event.route_index,
                ),
            )

    incomplete_shipments = set(shipments_by_id) - set(state.lead_times)
    state.late_shipments.update(incomplete_shipments)
    lead_times = [
        state.lead_times.get(shipment_id, planned_lead_time)
        for shipment_id, planned_lead_time in planned_lead_times.items()
    ]
    average_lead_time = (
        sum(lead_times) / len(lead_times)
        if lead_times
        else 0
    )
    delay_hours = [
        max(0, lead_time - horizon_hours)
        for lead_time in lead_times
    ]

    return SimulationResult(
        total_cost=state.total_cost,
        average_lead_time_hours=average_lead_time,
        average_delay_hours=(sum(delay_hours) / len(delay_hours) if delay_hours else 0),
        late_shipments=len(state.late_shipments),
        final_inventory=state.inventory,
    )
