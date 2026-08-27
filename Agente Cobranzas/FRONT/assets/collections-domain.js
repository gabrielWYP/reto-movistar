import { FEATURED_CASE_LIMIT } from "./collections-config.js";

const numeric = (value) => (Number.isFinite(Number(value)) ? Number(value) : 0);

export function sortPriorities(rows, sortBy = "priority_score") {
  return [...rows].sort((left, right) => {
    const difference = numeric(right[sortBy]) - numeric(left[sortBy]);
    return difference || String(left.customer || "").localeCompare(String(right.customer || ""));
  });
}

export function filterPriorities(rows, filters = {}) {
  return rows.filter((row) => {
    if (filters.priority && row.priority !== filters.priority) return false;
    if (filters.minDays && numeric(row.max_days_past_due) <= numeric(filters.minDays)) return false;
    if (filters.partial && numeric(row.partial_payment_invoice_count) < 1) return false;
    if (filters.overdueOnly && numeric(row.overdue_balance) <= 0) return false;
    if (filters.managedOnly && !filters.managedCustomers?.includes(row.customer)) return false;
    return true;
  });
}

export function featuredCases(rows, limit = FEATURED_CASE_LIMIT) {
  const ranked = sortPriorities(rows);
  const high = ranked.filter((row) => row.priority === "HIGH");
  if (high.length) {
    return {
      title: "Casos críticos",
      subtitle: `${high.length} cliente${high.length === 1 ? "" : "s"} de prioridad alta al corte.`,
      rows: high.slice(0, limit),
      showAllHigh: high.length > limit,
    };
  }
  return {
    title: "Sin casos críticos",
    subtitle: ranked.length ? "Casos a considerar según su severidad real." : "No hay saldo pendiente para priorizar.",
    rows: ranked.slice(0, limit),
    showAllHigh: false,
  };
}

export function filterExceptions(rows, filters = {}, operationalStates = {}) {
  return rows.filter((row) => {
    const state = operationalStates[row.case_id] || row.operational_state;
    if (filters.severity && row.severity !== filters.severity) return false;
    if (filters.state && state !== filters.state) return false;
    if (filters.type && row.type !== filters.type) return false;
    return true;
  });
}

export function caseState(row, operationalStates = {}) {
  return operationalStates[row.case_id] || row.operational_state || "PENDIENTE_VALIDACION";
}

export function primaryFinding(data) {
  const metrics = data.metrics || {};
  const largestBucket = [...(data.aging || [])].sort(
    (a, b) => numeric(b.outstanding_balance) - numeric(a.outstanding_balance),
  )[0];
  return {
    overdueBalance: numeric(metrics.overdue_balance),
    outstandingBalance: numeric(metrics.outstanding_balance),
    bucket: largestBucket?.bucket || null,
    bucketAmount: numeric(largestBucket?.outstanding_balance),
  };
}
