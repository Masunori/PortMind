/** Browser-local storage helpers for unpersisted hypothetical signal proposals. */

export const hypothesisStorageKey = "AEGIS.planning.hypotheses.v1";

export function parseHypotheses(raw) {
    if (!raw) return [];
    try {
        const value = JSON.parse(raw);
        if (!Array.isArray(value)) return [];
        return value.filter((item) => item && typeof item === "object"
            && typeof item.id === "string" && typeof item.signal_type === "string")
            .map((item) => ({ ...item, confirmed: item.confirmed === true }));
    } catch { return []; }
}

export function mergeHypotheses(current, incoming) {
    const byId = new Map(current.map((item) => [item.id, item]));
    for (const item of incoming) byId.set(item.id, { ...item, confirmed: true });
    return [...byId.values()].sort((left, right) => left.id.localeCompare(right.id));
}

export function removeHypothesis(current, id) {
    return current.filter((item) => item.id !== id);
}

export function toggleHypothesis(current, id) {
    return current.map((item) => item.id === id ? { ...item, confirmed: !item.confirmed } : item);
}
