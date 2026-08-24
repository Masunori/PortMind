export type EntityKind = "NODE" | "EDGE";
export type FieldType = "NUMBER" | "INTEGER" | "BOOLEAN" | "STRING" | "ENUM";
export type FieldBehavior = "STATIC" | "STATE" | "FLOW" | "METRIC";
export type RuleOperation = "SET" | "ADD" | "SUBTRACT" | "MULTIPLY" | "MIN" | "MAX";

export type FieldDefinition = {
    key: string;
    label: string;
    type: FieldType;
    required: boolean;
    default: unknown;
    unit: string | null;
    enum_values: string[];
    behavior: FieldBehavior;
};

export type EntitySchema = {
    id: string;
    name: string;
    entity_kind: EntityKind;
    current_version_id: string;
    version: number;
    fields: FieldDefinition[];
    created_at: string;
};

export type SimulationRule = {
    id: string;
    name: string;
    trigger: string;
    operation: RuleOperation;
    source: string;
    target_metric: string;
    enabled: boolean;
    created_at: string;
};

export type ChangeImpact = {
    entity_count: number;
    edge_count: number;
    shipment_count: number;
    disruption_count: number;
    alias_count: number;
    rule_count: number;
    blockers: string[];
};
