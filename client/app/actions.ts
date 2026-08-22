"use server";

import { refresh } from "next/cache";

import {
    injectPortCongestion,
    requestAllScenarioSimulations,
    requestBaselineSimulation,
    requestPlanComparison,
    requestPlanRanking,
    setDisruptionEnabled,
} from "@/lib/api";
import type { DisruptionActionState } from "@/types/disruption";
import type { SimulationActionState } from "@/types/simulation";
import type { ScenarioActionState } from "@/types/scenario";
import type {
    PlanComparisonActionState,
    PlanRankingActionState,
} from "@/types/plan";

export async function runBaselineSimulation(
    _previousState: SimulationActionState,
    _formData: FormData,
): Promise<SimulationActionState> {
    void _previousState;
    void _formData;

    try {
        return {
            result: await requestBaselineSimulation(),
            error: null,
        };
    } catch (error) {
        return {
            result: null,
            error: error instanceof Error ? error.message : "Simulation failed",
        };
    }
}

export async function injectBaselineDisruption(
    _previousState: DisruptionActionState,
    _formData: FormData,
): Promise<DisruptionActionState> {
    void _previousState;
    void _formData;

    try {
        const disruption = await injectPortCongestion();
        refresh();

        return {
            disruption,
            error: null,
        };
    } catch (error) {
        return {
            disruption: null,
            error: error instanceof Error ? error.message : "Disruption injection failed",
        };
    }
}

export async function toggleBaselineDisruption(
    _previousState: DisruptionActionState,
    formData: FormData,
): Promise<DisruptionActionState> {
    void _previousState;

    try {
        const enabled = formData.get("enabled") === "true";
        const disruption = await setDisruptionEnabled(
            "hai-phong-port-congestion",
            enabled,
        );
        refresh();

        return { disruption, error: null };
    } catch (error) {
        return {
            disruption: null,
            error: error instanceof Error ? error.message : "Disruption toggle failed",
        };
    }
}

export async function runAllScenarios(
    _previousState: ScenarioActionState,
    _formData: FormData,
): Promise<ScenarioActionState> {
    void _previousState;
    void _formData;

    try {
        return {
            results: await requestAllScenarioSimulations(),
            error: null,
        };
    } catch (error) {
        return {
            results: null,
            error: error instanceof Error ? error.message : "Scenario batch failed",
        };
    }
}

export async function compareContingencyPlans(
    _previousState: PlanComparisonActionState,
    _formData: FormData,
): Promise<PlanComparisonActionState> {
    void _previousState;
    void _formData;

    try {
        return {
            results: await requestPlanComparison(),
            error: null,
        };
    } catch (error) {
        return {
            results: null,
            error: error instanceof Error ? error.message : "Plan comparison failed",
        };
    }
}

export async function rankContingencyPlans(
    _previousState: PlanRankingActionState,
    formData: FormData,
): Promise<PlanRankingActionState> {
    void _previousState;

    try {
        return {
            result: await requestPlanRanking({
                cost: Number(formData.get("cost_weight")),
                delay: Number(formData.get("delay_weight")),
                risk: Number(formData.get("risk_weight")),
            }),
            error: null,
        };
    } catch (error) {
        return {
            result: null,
            error: error instanceof Error ? error.message : "Plan ranking failed",
        };
    }
}
