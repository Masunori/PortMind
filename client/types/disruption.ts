export type DisruptionType =
    | "PORT_CONGESTION"
    | "EDGE_CLOSURE"
    | "TRANSIT_DELAY"
    | "NODE_DELAY"
    | "CAPACITY_REDUCTION";

export type DisruptionEffects = {
    edge_disabled?: boolean;
    transit_time_multiplier?: number;
    node_handling_delay_hours?: number;
    handling_time_multiplier?: number;
    capacity_multiplier?: number;
};

export type Disruption = {
    id: string;
    type: DisruptionType;
    enabled: boolean;
    affected_node_ids: string[];
    affected_edge_ids: string[];
    start_time: number;
    end_time: number;
    effects: DisruptionEffects;
};

export type DisruptionActionState =
    | { disruption: Disruption; error: null }
    | { disruption: null; error: string | null };

export type ExposureAnalysis = {
    disruption_id: string;
    affected_nodes: string[];
    affected_edges: string[];
    affected_shipments: string[];
    affected_customers: string[];
};
