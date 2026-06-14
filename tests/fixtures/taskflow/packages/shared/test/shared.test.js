import { test } from "node:test";
import assert from "node:assert/strict";
import { validateTask, normalizePriority } from "../index.js";

test("validateTask rejects empty title", () => {
  assert.equal(validateTask({ title: "" }), false);
  assert.equal(validateTask({ title: "ok" }), true);
});

test("validateTask rejects bad priority", () => {
  assert.equal(validateTask({ title: "ok", priority: "urgent" }), false);
  assert.equal(validateTask({ title: "ok", priority: "high" }), true);
});

test("normalizePriority defaults to med", () => {
  assert.equal(normalizePriority(null), "med");
  assert.equal(normalizePriority("low"), "low");
});
