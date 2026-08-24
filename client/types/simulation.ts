export type SimulationResult = {
    total_cost: number;
    average_lead_time_hours: number;
    average_delay_hours: number;
    late_shipments: number;
    final_inventory: Record<string, number>;
    custom_metrics: Record<string, number>;
};

export type SimulationActionState =
    | { result: SimulationResult; error: null }
    | { result: null; error: string | null };
