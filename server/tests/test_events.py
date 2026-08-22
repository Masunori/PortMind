"""Tests for deterministic simulation-event ordering."""

import heapq

from app.simulation.events import EventType, SimulationEvent


def test_events_are_ordered_by_time_then_sequence() -> None:
    """The heap resolves equal timestamps using insertion sequence."""

    queue = [
        SimulationEvent(12, 1, "shipment-2", EventType.ARRIVAL, 1),
        SimulationEvent(12, 0, "shipment-1", EventType.ARRIVAL, 1),
        SimulationEvent(4, 2, "shipment-3", EventType.ARRIVAL, 1),
    ]
    heapq.heapify(queue)

    assert [heapq.heappop(queue).shipment_id for _ in range(3)] == [
        "shipment-3",
        "shipment-1",
        "shipment-2",
    ]
