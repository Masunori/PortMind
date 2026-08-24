import type { Disruption, ExposureAnalysis } from "@/types/disruption";
import type { Scenario } from "@/types/scenario";
import type { Plan } from "@/types/plan";

export type Node = {
    id: string;
    name: string;
    type: string;
    inventory: number;
    capacity: number;
    schema_version_id: string | null;
    attributes: Record<string, unknown>;
};

export type Edge = {
    id: string;
    source_id: string;
    target_id: string;
    mode: string;
    transit_time_hours: number;
    cost: number;
    capacity: number;
    schema_version_id: string | null;
    attributes: Record<string, unknown>;
};

export type Shipment = {
    id: string;
    origin_id: string;
    destination_id: string;
    quantity: number;
    current_node_id: string;
    route: string[];
    expected_arrival: string;
};

export type Network = {
    nodes: Node[];
    edges: Edge[];
};

export type NetworkResponse = {
    network: Network;
    shipments: Shipment[];
    disruptions: Disruption[];
    exposures: ExposureAnalysis[];
    scenarios: Scenario[];
    plans: Plan[];
};
