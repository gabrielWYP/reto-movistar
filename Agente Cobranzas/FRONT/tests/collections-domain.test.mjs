import assert from "node:assert/strict";
import test from "node:test";

import {
  featuredCases,
  filterExceptions,
  filterPriorities,
  sortPriorities,
} from "../assets/collections-domain.js";

test("featured cases never promote medium cases to high", () => {
  const result = featuredCases([
    { customer: "B", priority: "MEDIUM", priority_score: 40 },
    { customer: "A", priority: "LOW", priority_score: 20 },
  ]);
  assert.equal(result.title, "Sin casos críticos");
  assert.deepEqual(result.rows.map((row) => row.priority), ["MEDIUM", "LOW"]);
});

test("featured cases show only real high cases and cap the initial view", () => {
  const rows = Array.from({ length: 5 }, (_, index) => ({
    customer: `C${index}`,
    priority: index < 4 ? "HIGH" : "MEDIUM",
    priority_score: 100 - index,
  }));
  const result = featuredCases(rows);
  assert.equal(result.rows.length, 3);
  assert.ok(result.rows.every((row) => row.priority === "HIGH"));
  assert.equal(result.showAllHigh, true);
});

test("priority sorting and filters do not change scores or severities", () => {
  const rows = [
    { customer: "A", priority: "HIGH", priority_score: 80, overdue_balance: 10, max_days_past_due: 20, partial_payment_invoice_count: 0 },
    { customer: "B", priority: "MEDIUM", priority_score: 50, overdue_balance: 90, max_days_past_due: 70, partial_payment_invoice_count: 1 },
  ];
  const sorted = sortPriorities(rows, "overdue_balance");
  const filtered = filterPriorities(rows, { minDays: 60, partial: true, overdueOnly: true });
  assert.equal(sorted[0].customer, "B");
  assert.deepEqual(filtered.map((row) => row.customer), ["B"]);
  assert.equal(rows[0].priority_score, 80);
  assert.equal(rows[0].priority, "HIGH");
});

test("documentary cases filter by local operational state", () => {
  const rows = [{ case_id: "1", severity: "MEDIUM", type: "X", operational_state: "PENDIENTE_VALIDACION" }];
  assert.equal(filterExceptions(rows, { state: "EN_REVISION" }, { "1": "EN_REVISION" }).length, 1);
});
