import type { LocalHypothesis } from "../types/planning";

export const hypothesisStorageKey: string;
export function parseHypotheses(raw: string | null): LocalHypothesis[];
export function mergeHypotheses(current: LocalHypothesis[], incoming: LocalHypothesis[]): LocalHypothesis[];
export function removeHypothesis(current: LocalHypothesis[], id: string): LocalHypothesis[];
export function toggleHypothesis(current: LocalHypothesis[], id: string): LocalHypothesis[];
