import test from "node:test";
import assert from "node:assert/strict";

import {
    mergeHypotheses, parseHypotheses, removeHypothesis, toggleHypothesis,
} from "../lib/hypothesis-store.mjs";

const hypothesis = (id, confirmed = false) => ({ id, name: id,
    classification: "HYPOTHETICAL", signal_type: "DELAY", payload: {},
    occurrence_probability: 0.5, rationale: "test", metadata: {}, confirmed });

test("malformed local storage is ignored safely", () => {
    assert.deepEqual(parseHypotheses("not-json"), []);
    assert.deepEqual(parseHypotheses(JSON.stringify({ id: "wrong" })), []);
});

test("new hypotheses are confirmed and merged deterministically", () => {
    const result = mergeHypotheses([hypothesis("b")], [hypothesis("a")]);
    assert.deepEqual(result.map((item) => item.id), ["a", "b"]);
    assert.equal(result[0].confirmed, true);
});

test("browser hypotheses can be toggled and removed", () => {
    const toggled = toggleHypothesis([hypothesis("a")], "a");
    assert.equal(toggled[0].confirmed, true);
    assert.deepEqual(removeHypothesis(toggled, "a"), []);
});
