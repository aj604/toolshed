import { test } from "node:test";
import assert from "node:assert/strict";
import { overBudget, formatKb } from "../src/budget.js";

test("overBudget compares against kb threshold", () => {
  assert.equal(overBudget(2048, 1), true);
  assert.equal(overBudget(512, 1), false);
});

test("formatKb renders one decimal", () => {
  assert.equal(formatKb(1536), "1.5kb");
});
