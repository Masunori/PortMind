"""Provider-neutral LangGraph orchestration for supply-chain response runs."""

from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.interpreter import EventInterpreter, InterpretSignalRequest
from app.agents.planner import ContingencyPlanner, PlanningContext
from app.agents.scenario_generator import (
    ScenarioGenerationContext,
    ScenarioGenerator,
)
from app.ai import AIProvider
from app.ai.schemas import InterpretedSignal
from app.domain.disruption import Disruption, DisruptionEffects, DisruptionType
from app.domain.exposure import ExposureAnalysis
from app.domain.grounding import GroundedSignal
from app.domain.plan import Plan, PlanScenarioResult
from app.domain.ranking import PlanRankingResult, RankingWeights
from app.domain.run import RunEventType
from app.domain.scenario import Scenario
from app.services.entity_resolution import ground_interpreted_signal
from app.services.exposure_service import analyze_exposure
from app.services.network_service import get_network
from app.services.plan_service import compare_plan_scenario_sets
from app.services.ranking_service import rank_plan_results


class OrchestratorState(TypedDict, total=False):
    """Carry validated state between provider-neutral workflow nodes."""

    raw_signal: str
    interpreted_signal: InterpretedSignal | None
    grounded_signal: GroundedSignal | None
    disruption: Disruption | None
    exposure: ExposureAnalysis | None
    scenarios: list[Scenario]
    plans: list[Plan]
    results: list[PlanScenarioResult]
    ranking: PlanRankingResult | None


def _build_disruption(grounded: GroundedSignal) -> Disruption | None:
    """Convert grounded locations into a deterministic closure disruption."""

    if not grounded.node_ids:
        return None
    network = get_network()
    affected_nodes = set(grounded.node_ids)
    outbound_edges = sorted(
        edge.id
        for edge in network.edges
        if edge.source_id in affected_nodes
        and edge.id in set(grounded.edge_ids)
    )
    signal = grounded.interpreted_signal
    duration = signal.expected_duration_max_hours or 24
    if outbound_edges:
        return Disruption(
            id="interpreted-edge-closure",
            type=DisruptionType.EDGE_CLOSURE,
            affected_edge_ids=outbound_edges,
            start_time=0,
            end_time=duration,
            effects=DisruptionEffects(edge_disabled=True),
        )
    return Disruption(
        id="interpreted-node-delay",
        type=DisruptionType.PORT_CONGESTION,
        affected_node_ids=sorted(affected_nodes),
        start_time=0,
        end_time=duration,
        effects=DisruptionEffects(
            handling_time_multiplier=1 + (signal.severity or 0.5)
        ),
    )


EventSink = Callable[[RunEventType, dict[str, object]], None]


def build_orchestrator(
    provider: AIProvider,
    event_sink: EventSink | None = None,
):
    """Compile the complete local workflow around an abstract AI provider."""

    interpreter = EventInterpreter(provider)
    scenario_generator = ScenarioGenerator(provider)
    planner = ContingencyPlanner(provider)

    def emit(event_type: RunEventType, payload: dict[str, object]) -> None:
        """Forward an observable milestone when a sink is configured."""

        if event_sink is not None:
            event_sink(event_type, payload)

    async def interpret_signal(state: OrchestratorState) -> OrchestratorState:
        """Interpret raw signal text into a validated human-readable event."""

        interpreted = await interpreter.interpret(
            InterpretSignalRequest(text=state["raw_signal"])
        )
        emit(
            RunEventType.SIGNAL_INTERPRETED,
            {"event_type": interpreted.event_type},
        )
        return {"interpreted_signal": interpreted}

    async def ground_entities(state: OrchestratorState) -> OrchestratorState:
        """Resolve interpreted names and build a grounded disruption."""

        interpreted = state.get("interpreted_signal")
        if interpreted is None:
            raise ValueError("Cannot ground a missing interpreted signal")
        grounded = ground_interpreted_signal(interpreted)
        emit(
            RunEventType.ENTITIES_GROUNDED,
            {
                "node_ids": grounded.node_ids,
                "unresolved_locations": grounded.unresolved_locations,
            },
        )
        return {
            "grounded_signal": grounded,
            "disruption": _build_disruption(grounded),
        }

    async def analyze_impact(state: OrchestratorState) -> OrchestratorState:
        """Traverse downstream exposure for the grounded disruption."""

        disruption = state.get("disruption")
        if disruption is None:
            emit(RunEventType.EXPOSURE_ANALYZED, {"affected_shipments": 0})
            return {"exposure": None}
        exposure = analyze_exposure(disruption)
        emit(
            RunEventType.EXPOSURE_ANALYZED,
            {"affected_shipments": len(exposure.affected_shipments)},
        )
        return {"exposure": exposure}

    async def route_impact(state: OrchestratorState) -> str:
        """Skip generation when no shipment has significant exposure."""

        exposure = state.get("exposure")
        return "significant" if exposure and exposure.affected_shipments else "end"

    async def generate_scenarios(state: OrchestratorState) -> OrchestratorState:
        """Generate validated scenario assumptions for exposed entities."""

        disruption = state.get("disruption")
        exposure = state.get("exposure")
        if disruption is None or exposure is None:
            raise ValueError("Scenario generation requires disruption and exposure")
        scenarios = await scenario_generator.generate(
            ScenarioGenerationContext(disruption=disruption, exposure=exposure)
        )
        emit(RunEventType.SCENARIOS_GENERATED, {"count": len(scenarios)})
        return {"scenarios": scenarios}

    async def generate_plans(state: OrchestratorState) -> OrchestratorState:
        """Generate capability-validated plans for exposed shipments."""

        exposure = state.get("exposure")
        if exposure is None:
            raise ValueError("Plan generation requires exposure")
        plans = await planner.generate(PlanningContext(exposure=exposure))
        emit(RunEventType.PLANS_GENERATED, {"count": len(plans)})
        return {"plans": plans}

    async def simulate_matrix(state: OrchestratorState) -> OrchestratorState:
        """Run every validated plan against every validated scenario."""

        plans = state.get("plans", [])
        scenarios = state.get("scenarios", [])
        total = len(plans) * len(scenarios)
        emit(RunEventType.SIMULATION_STARTED, {"total": total})

        def completed(
            count: int,
            total_count: int,
            result: PlanScenarioResult,
        ) -> None:
            """Emit progress after each deterministic matrix cell."""

            emit(
                RunEventType.SIMULATION_COMPLETED,
                {
                    "completed": count,
                    "total": total_count,
                    "plan_id": result.plan_id,
                    "scenario_id": result.scenario_id,
                },
            )

        results = compare_plan_scenario_sets(
            plans,
            scenarios,
            on_result=completed,
        )
        return {"results": results}

    async def rank(state: OrchestratorState) -> OrchestratorState:
        """Rank deterministic matrix results with default local weights."""

        ranking = rank_plan_results(
            state.get("results", []),
            RankingWeights(delay=300),
        )
        emit(
            RunEventType.RANKING_COMPLETED,
            {"recommended_plan": ranking.recommended_plan},
        )
        return {"ranking": ranking}

    graph = StateGraph(OrchestratorState)
    graph.add_node("interpret_signal", interpret_signal)
    graph.add_node("ground_entities", ground_entities)
    graph.add_node("analyze_exposure", analyze_impact)
    graph.add_node("generate_scenarios", generate_scenarios)
    graph.add_node("generate_plans", generate_plans)
    graph.add_node("simulate_matrix", simulate_matrix)
    graph.add_node("rank", rank)
    graph.add_edge(START, "interpret_signal")
    graph.add_edge("interpret_signal", "ground_entities")
    graph.add_edge("ground_entities", "analyze_exposure")
    graph.add_conditional_edges(
        "analyze_exposure",
        route_impact,
        {"significant": "generate_scenarios", "end": END},
    )
    graph.add_edge("generate_scenarios", "generate_plans")
    graph.add_edge("generate_plans", "simulate_matrix")
    graph.add_edge("simulate_matrix", "rank")
    graph.add_edge("rank", END)
    return graph.compile()
