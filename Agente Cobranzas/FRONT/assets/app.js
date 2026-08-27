import {
  ACTION_LABELS, API_BASE, API_LIST_LIMIT, BUCKET_LABELS, FINDING_LABELS,
  INVOICE_STATES, OPERATIONAL_STATES, PROCESS_META, SEVERITY_META, SORT_OPTIONS, VIEW_META,
} from "./collections-config.js";
import {
  caseState, featuredCases, filterExceptions, filterPriorities, primaryFinding, sortPriorities,
} from "./collections-domain.js";

const SESSION_KEY = "sonia.collections.workbench.v1";
const providerText = { "opencode-go": "OpenCode Go" };
const cache = new Map();
const initialState = {
  view: "portfolio", process: "collection", asOf: "", customer: "", invoice: "",
  sortBy: "priority_score", priorityFilters: {}, exceptionFilters: {},
  customerInvoiceFilter: "open", operationalStates: {}, invoiceStates: {}, managedCustomers: [], history: [],
};

function restoreState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
    return saved && typeof saved === "object" ? { ...initialState, ...saved, history: [] } : { ...initialState };
  } catch { return { ...initialState }; }
}

const state = restoreState();
let currentData = null;
let currentCases = [];
const byId = (id) => document.getElementById(id);
const content = byId("content");
const controls = byId("controls");
const feedback = byId("feedback");

function persistState() {
  try {
    const { history: _history, ...persisted } = state;
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(persisted));
  } catch { /* Session state is optional. */ }
}

function escapeHtml(value) {
  return String(value ?? "—").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function money(value) {
  if (typeof value !== "number") return "—";
  return new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN" }).format(value);
}

function dateText(value) {
  if (!value) return "No disponible";
  const parts = String(value).split("-");
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : String(value);
}

const whole = (value) => typeof value === "number" ? new Intl.NumberFormat("es-PE").format(value) : "—";
const percent = (value) => typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
const score = (value) => `${Number(value || 0).toFixed(1)} / 100`;

function metaFor(value) {
  return SEVERITY_META[value] || { label: String(value || "Sin estado"), tone: "neutral", icon: "•" };
}

function badge(value, label) {
  const meta = metaFor(value);
  return `<span class="badge tone-${meta.tone}"><span aria-hidden="true">${escapeHtml(meta.icon)}</span> ${escapeHtml(label || meta.label)}</span>`;
}

function operationalBadge(value) {
  const meta = OPERATIONAL_STATES[value] || OPERATIONAL_STATES.PENDIENTE_VALIDACION;
  return `<span class="badge tone-${meta.tone}">${escapeHtml(meta.label)}</span>`;
}

function invoiceStateBadge(document) {
  const value = state.invoiceStates[document];
  if (!value) return "";
  const meta = INVOICE_STATES[value];
  return `<span class="badge tone-${meta.tone}">${escapeHtml(meta.label)}</span>`;
}

function setNotice(message, type = "") {
  feedback.className = `notice ${type}`.trim();
  feedback.textContent = message;
}

function errorMessage(payload, fallback) {
  const detail = payload?.detail ?? payload?.error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail?.errors)) return detail.errors.join(" ");
  return fallback;
}

function button(label, action, attributes = "", variant = "secondary") {
  return `<button class="${variant}" type="button" data-action="${escapeHtml(action)}" ${attributes}>${escapeHtml(label)}</button>`;
}

function table(headers, rows, emptyMessage = "No hay registros para mostrar.") {
  if (!rows.length) return `<div class="empty"><strong>Sin resultados</strong><span>${escapeHtml(emptyMessage)}</span></div>`;
  return `<div class="table-wrap"><table><thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

function technicalDetails(data) {
  return `<details class="technical"><summary>Detalle técnico e integración (JSON)</summary><pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre></details>`;
}

function snapshot() {
  return { view: state.view, process: state.process, customer: state.customer, invoice: state.invoice,
    priorityFilters: { ...state.priorityFilters }, exceptionFilters: { ...state.exceptionFilters }, sortBy: state.sortBy };
}

async function navigate(view, context = {}, remember = true) {
  if (remember && state.view !== view) state.history.push(snapshot());
  Object.assign(state, context, { view, process: VIEW_META[view].process });
  persistState(); renderNavigation(); renderControls(); await loadView();
}

async function goBack() {
  const previous = state.history.pop();
  if (!previous) return navigate(state.process === "revenue" ? "exceptions" : "portfolio", {}, false);
  Object.assign(state, previous); renderNavigation(); renderControls(); await loadView();
}

function renderNavigation() {
  document.querySelectorAll("[data-process]").forEach((item) => {
    const active = item.dataset.process === state.process;
    item.classList.toggle("active", active); item.setAttribute("aria-pressed", String(active));
  });
  document.querySelector(".nav").innerHTML = PROCESS_META[state.process].views.map((view) =>
    `<button class="${state.view === view ? "active" : ""}" data-action="navigate" data-view="${view}" type="button">${escapeHtml(VIEW_META[view].label)}</button>`).join("");
  byId("workspace-heading").innerHTML = `<div><span class="workspace-kicker">${escapeHtml(PROCESS_META[state.process].label)}</span><h2>${escapeHtml(VIEW_META[state.view].label)}</h2><p>${escapeHtml(PROCESS_META[state.process].description)}</p></div>`;
  byId("breadcrumbs").innerHTML = state.history.length
    ? `${button("← Volver", "back", "", "text-button")}<span>${escapeHtml(VIEW_META[state.view].label)}</span>`
    : `<span>${escapeHtml(VIEW_META[state.view].label)}</span>`;
}

function renderControls() {
  let contextual = "";
  if (state.view === "customer") contextual = `<div class="field compact"><label for="entity">Buscar cliente</label><input id="entity" value="${escapeHtml(state.customer)}" placeholder="Código o razón social"></div>`;
  if (state.view === "invoice") contextual = `<div class="field compact"><label for="entity">Buscar factura</label><input id="entity" value="${escapeHtml(state.invoice)}" placeholder="Número de factura"></div>`;
  controls.innerHTML = `<div class="controls"><div class="field compact"><label for="asof">Fecha de corte</label><input id="asof" type="date" value="${escapeHtml(state.asOf)}"><span class="help">Fuente publicada por Supervisor.</span></div>${contextual}${button("Actualizar", "refresh", "", "primary")}</div>`;
}

const metricLabels = {
  total_billed: "Facturado", total_paid_linked: "Pagos aplicados", outstanding_balance: "Saldo pendiente",
  overdue_balance: "Saldo vencido", collection_ratio: "Cobranza aplicada / facturación",
  collection_ratio_30_days: "Cobrado dentro de 30 días", average_collection_period_days: "Periodo medio de cobro",
  priority_score: "Índice de prioridad", payment_applications_analyzed: "Aplicaciones analizadas",
  partial_payment_invoice_count: "Facturas con pago parcial", exception_count: "Casos por validar",
  high_priority_exception_count: "Casos de prioridad alta",
};

function metricValue(key, value) {
  if (["collection_ratio", "collection_ratio_30_days"].includes(key)) return percent(value);
  if (key === "average_collection_period_days") return value == null ? "No disponible" : `${Number(value).toFixed(1)} días`;
  if (key === "priority_score") return score(value);
  if (["payment_applications_analyzed", "partial_payment_invoice_count", "exception_count", "high_priority_exception_count"].includes(key)) return whole(value);
  return money(value);
}

function metricCards(metrics, clickable = {}) {
  return `<div class="cards">${Object.keys(metricLabels).filter((key) => key in metrics).map((key) => {
    const action = clickable[key]; const tag = action ? "button" : "div";
    return `<${tag} class="card ${action ? "card-action" : ""}" ${action ? `type="button" data-action="${action}"` : ""}><span>${escapeHtml(metricLabels[key])}</span><strong>${metricValue(key, metrics[key])}</strong>${action ? "<small>Ver detalle →</small>" : ""}</${tag}>`;
  }).join("")}</div>`;
}

function renderAging(rows) {
  if (!rows.length) return "";
  const maximum = Math.max(...rows.map((row) => Number(row.outstanding_balance || 0)), 1);
  return `<section class="section"><div class="section-title"><div><h3>Antigüedad de la deuda</h3><p>Saldo calculado por el backend según días desde el vencimiento.</p></div></div><div class="aging-list">${rows.map((row) => `<div class="aging-row"><div class="aging-label"><strong>${escapeHtml(BUCKET_LABELS[row.bucket] || row.bucket)}</strong><span>${whole(row.documents)} factura${row.documents === 1 ? "" : "s"}</span></div><div class="aging-track" aria-label="${escapeHtml(BUCKET_LABELS[row.bucket] || row.bucket)}: ${escapeHtml(money(row.outstanding_balance))}"><span style="width:${Math.max(3, Number(row.outstanding_balance || 0) / maximum * 100).toFixed(1)}%"></span></div><strong>${money(row.outstanding_balance)}</strong></div>`).join("")}</div></section>`;
}

function renderFindings(rows) {
  if (!rows?.length) return "";
  return `<section class="section"><div class="section-title"><div><h3>Situaciones identificadas</h3><p>Hallazgos respaldados por el corte; no son errores confirmados.</p></div></div>${table(["Situación", "Severidad", "Explicación", "Importe", "Casos"], rows.map((row) => `<tr><td><strong>${escapeHtml(FINDING_LABELS[row.type] || row.type)}</strong></td><td>${badge(row.severity)}</td><td>${escapeHtml(row.message)}</td><td>${row.amount == null ? "—" : money(row.amount)}</td><td>${row.count == null ? "—" : whole(row.count)}</td></tr>`))}</section>`;
}

function actionDestination(action) {
  if (["review_unmatched_payments", "review_overapplication", "review_exceptions"].includes(action)) return "exceptions";
  if (["review_collection_priorities", "assign_collection_queue", "start_collection", "prioritize_internal_management"].includes(action)) return "priorities";
  return null;
}

function renderRecommendedActions(rows = []) {
  if (!rows.length) return "";
  return `<section class="section"><div class="section-title"><div><h3>Siguientes acciones</h3><p>Acciones internas de análisis; no ejecutan cobros ni comunicaciones.</p></div></div><div class="action-grid">${rows.map((row) => { const destination = actionDestination(row.action); return `<article class="action-card"><div><strong>${escapeHtml(ACTION_LABELS[row.action] || row.action)}</strong><p>${escapeHtml(row.reason || "")}</p></div>${destination ? button("Abrir", "navigate", `data-view="${destination}"`) : ""}</article>`; }).join("")}</div></section>`;
}

function renderPortfolio(data) {
  const finding = primaryFinding(data);
  const text = finding.overdueBalance > 0
    ? `${money(finding.overdueBalance)} del saldo pendiente ya está vencido${finding.bucket ? ` y la mayor concentración está en “${BUCKET_LABELS[finding.bucket] || finding.bucket}”` : ""}.`
    : "No se observa saldo vencido en la fecha de corte seleccionada.";
  return `<section class="headline-finding"><span>Hallazgo principal del corte</span><strong>${escapeHtml(text)}</strong><small>Derivado de saldos y aging calculados por el agente.</small></section>${metricCards(data.metrics || {}, { overdue_balance: "overdue-cases", partial_payment_invoice_count: "partial-cases" })}${renderAging(data.aging || [])}${renderFindings(data.findings || [])}${renderRecommendedActions(data.recommended_actions)}${technicalDetails(data)}`;
}

function priorityFilterBar() {
  const active = state.priorityFilters;
  const chip = (label, key, value = true) => `<button class="filter-chip ${active[key] === value ? "active" : ""}" type="button" data-action="priority-filter" data-filter="${key}" data-value="${escapeHtml(value)}">${escapeHtml(label)}</button>`;
  return `<div class="toolbar"><div class="filter-group">${chip("Alta", "priority", "HIGH")}${chip("Media", "priority", "MEDIUM")}${chip(">30 días", "minDays", "30")}${chip(">60 días", "minDays", "60")}${chip("Pago parcial", "partial")}${chip("Solo saldo vencido", "overdueOnly")}${button("Limpiar filtros", "clear-priority-filters", "", "text-button")}</div><label class="select-field">Ordenar por<select id="priority-sort">${SORT_OPTIONS.map((item) => `<option value="${item.value}" ${state.sortBy === item.value ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}</select></label></div>`;
}

function renderFeatured(rows) {
  const featured = featuredCases(rows);
  return `<section class="section featured"><div class="section-title"><div><h3>${escapeHtml(featured.title)}</h3><p>${escapeHtml(featured.subtitle)}</p></div>${featured.showAllHigh ? button("Ver todos los casos de alta prioridad", "show-all-high", "", "text-button") : ""}</div><div class="featured-grid">${featured.rows.map((row) => `<article class="priority-card"><div class="priority-card-top">${badge(row.priority)}<strong>${score(row.priority_score)}</strong></div><h4>${escapeHtml(row.customer)}</h4><dl><div><dt>Saldo vencido</dt><dd>${money(row.overdue_balance)}</dd></div><div><dt>Mayor atraso</dt><dd>${whole(row.max_days_past_due)} días</dd></div></dl>${button("Ver caso", "open-customer", `data-customer="${escapeHtml(row.customer)}"`, "primary")}</article>`).join("")}</div></section>`;
}

function renderPriorities(data) {
  const ranked = sortPriorities(data.evidence || [], state.sortBy);
  const filtered = filterPriorities(ranked, { ...state.priorityFilters, managedCustomers: state.managedCustomers });
  const rows = filtered.map((row, index) => `<tr class="clickable-row" tabindex="0" data-action="open-customer" data-customer="${escapeHtml(row.customer)}"><td>${whole(index + 1)}</td><td><strong>${escapeHtml(row.customer)}</strong></td><td>${money(row.outstanding_balance)}</td><td>${money(row.overdue_balance)}</td><td>${whole(row.max_days_past_due)} días</td><td>${percent(row.overdue_share)}</td><td>${score(row.priority_score)}</td><td>${badge(row.priority)}</td><td><div class="row-actions">${button("Ver cliente", "open-customer", `data-customer="${escapeHtml(row.customer)}"`, "text-button")}${button(state.managedCustomers.includes(row.customer) ? "En gestión" : "Marcar para gestión", "toggle-managed", `data-customer="${escapeHtml(row.customer)}"`, "text-button")}</div></td></tr>`);
  const scoring = (data.findings || []).find((item) => item.type === "SCORING_RULE");
  return `${renderFeatured(ranked)}<section class="section"><div class="section-title"><div><h3>Ranking completo</h3><p>${whole(filtered.length)} de ${whole(data.metrics?.customers_ranked)} clientes visibles.</p></div></div>${priorityFilterBar()}${table(["Posición", "Cliente", "Saldo", "Vencido", "Mayor atraso", "% vencido", "Índice", "Prioridad", "Acciones"], rows, "No hay clientes que coincidan con los filtros.")}<details><summary>Cómo se calcula la prioridad</summary><p>${escapeHtml(scoring?.message || "La prioridad y sus componentes son calculados por el backend.")}</p><p>El orden visual no modifica el índice ni la severidad.</p></details></section>${technicalDetails(data)}`;
}

function customerInvoiceRows(data) {
  let rows = [...(data.evidence || [])];
  if (state.customerInvoiceFilter === "open") rows = rows.filter((row) => Number(row.outstanding_balance) > 0);
  if (state.customerInvoiceFilter === "overdue") rows = rows.filter((row) => Number(row.outstanding_balance) > 0 && Number(row.days_past_due) > 0);
  if (state.customerInvoiceFilter === "partial") rows = rows.filter((row) => row.settlement_state === "PAGO_PARCIAL");
  return rows.sort((a, b) => Number(b.outstanding_balance || 0) - Number(a.outstanding_balance || 0));
}

function renderCustomer(data) {
  const rows = customerInvoiceRows(data); const priority = data.status?.priority || "LOW"; const nextAction = data.recommended_actions?.[0];
  return `<section class="executive-header"><div><span>Estado del cliente</span><h3>${escapeHtml(data.entity?.id)}</h3></div><div><span>Prioridad</span>${badge(priority)}</div><div><span>Saldo vencido</span><strong>${money(data.metrics?.overdue_balance)}</strong></div><div><span>Siguiente acción</span><strong>${escapeHtml(ACTION_LABELS[nextAction?.action] || nextAction?.action || "Mantener seguimiento")}</strong></div></section>${metricCards(data.metrics || {})}${renderAging(data.aging || [])}${renderFindings(data.findings || [])}<section class="section"><div class="section-title"><div><h3>Facturas por gestionar</h3><p>Selecciona una fila para revisar trazabilidad, pagos y evidencia.</p></div></div><div class="filter-group">${["open", "overdue", "partial", "all"].map((value) => `<button class="filter-chip ${state.customerInvoiceFilter === value ? "active" : ""}" data-action="invoice-filter" data-value="${value}" type="button">${{ open: "Con saldo", overdue: "Vencidas", partial: "Pago parcial", all: "Todas" }[value]}</button>`).join("")}</div>${table(["Factura", "Vencimiento", "Atraso", "Facturado", "Pagos", "Saldo", "Estado", "Aplicación", "Acciones"], rows.map((row) => `<tr class="clickable-row" tabindex="0" data-action="open-invoice" data-invoice="${escapeHtml(row.document)}"><td><strong>${escapeHtml(row.document)}</strong></td><td>${dateText(row.due_at)}</td><td>${whole(row.days_past_due)} días</td><td>${money(row.invoice_total)}</td><td>${money(row.paid)}</td><td>${money(row.outstanding_balance)}</td><td>${badge(row.settlement_state)}</td><td>${badge(row.reconciliation_state)}</td><td><div class="row-actions">${button("Ver factura", "open-invoice", `data-invoice="${escapeHtml(row.document)}"`, "text-button")}${button("Priorizar", "toggle-managed", `data-customer="${escapeHtml(row.customer)}"`, "text-button")}${button("Pendiente", "invoice-state", `data-invoice="${escapeHtml(row.document)}" data-state="PENDIENTE_GESTION"`, "text-button")}${button("Revisado", "invoice-state", `data-invoice="${escapeHtml(row.document)}" data-state="REVISADO"`, "text-button")}${invoiceStateBadge(row.document)}${row.reconciliation_state === "REQUIERE_REVISION" ? button("Abrir conciliación", "open-exceptions", `data-invoice="${escapeHtml(row.document)}"`, "text-button") : ""}</div></td></tr>`), "No hay facturas para el filtro seleccionado.")}</section>${technicalDetails(data)}`;
}

function renderInvoice(data) {
  const row = data.evidence?.[0] || {}; const payments = row.payments || []; const credits = row.credit_note_documents || []; const hasCase = Number(row.reconciliation_case_count || 0) > 0;
  return `<div class="context-actions">${button("Ver cliente", "open-customer", `data-customer="${escapeHtml(row.customer)}"`)}${hasCase ? button("Ir a conciliación documental", "open-exceptions", `data-invoice="${escapeHtml(row.document)}"`, "primary") : ""}</div><section class="document-summary"><div><span>Documento</span><h3>${escapeHtml(row.document)}</h3><small>Cliente ${escapeHtml(row.customer)} · Cuenta ${escapeHtml(row.account_code)}</small></div><div class="status-stack">${badge(data.status?.settlement)}${badge(data.status?.delinquency)}${badge(data.status?.reconciliation)}</div></section>${metricCards(data.metrics || {})}${renderFindings(data.findings || [])}<section class="section"><h3>Resumen del documento</h3>${table(["Emisión", "Vencimiento", "Facturado", "Notas de crédito", "Pagos", "Saldo"], [`<tr><td>${dateText(row.issued_at)}</td><td>${dateText(row.due_at)}</td><td>${money(row.invoice_total)}</td><td>${money(row.credit_notes)}</td><td>${money(row.paid)}</td><td><strong>${money(row.outstanding_balance)}</strong></td></tr>`])}</section><section class="section"><h3>Pagos aplicados</h3>${table(["Fecha", "Importe aplicado", "Cuenta"], payments.map((payment) => `<tr><td>${dateText(payment.paid_at)}</td><td>${money(payment.amount)}</td><td>${escapeHtml(payment.account_code)}</td></tr>`), "No existen pagos aplicados a esta factura al corte.")}</section>${credits.length ? `<section class="section"><h3>Notas de crédito relacionadas</h3>${table(["Documento", "Fecha", "Importe"], credits.map((credit) => `<tr><td>${escapeHtml(credit.document)}</td><td>${dateText(credit.issued_at)}</td><td>${money(credit.amount)}</td></tr>`))}</section>` : ""}${renderRecommendedActions(data.recommended_actions)}${technicalDetails(data)}`;
}

function exceptionFilterBar(rows) {
  const types = [...new Set(rows.map((row) => row.type))];
  return `<div class="toolbar"><div class="filter-group"><button class="filter-chip ${state.exceptionFilters.severity === "HIGH" ? "active" : ""}" data-action="exception-filter" data-filter="severity" data-value="HIGH" type="button">Alta</button><button class="filter-chip ${state.exceptionFilters.severity === "MEDIUM" ? "active" : ""}" data-action="exception-filter" data-filter="severity" data-value="MEDIUM" type="button">Media</button>${button("Limpiar filtros", "clear-exception-filters", "", "text-button")}</div><div class="select-row"><label class="select-field">Estado<select id="exception-state"><option value="">Todos</option>${Object.entries(OPERATIONAL_STATES).map(([value, meta]) => `<option value="${value}" ${state.exceptionFilters.state === value ? "selected" : ""}>${escapeHtml(meta.label)}</option>`).join("")}</select></label><label class="select-field">Situación<select id="exception-type"><option value="">Todas</option>${types.map((value) => `<option value="${escapeHtml(value)}" ${state.exceptionFilters.type === value ? "selected" : ""}>${escapeHtml(FINDING_LABELS[value] || value)}</option>`).join("")}</select></label></div></div>`;
}

function renderExceptions(data) {
  currentCases = data.evidence || [];
  const filters = { ...state.exceptionFilters };
  let filtered = filterExceptions(currentCases, filters, state.operationalStates);
  if (filters.document) filtered = filtered.filter((row) => row.document === filters.document);
  const rows = filtered.map((row) => `<tr class="clickable-row" tabindex="0" data-action="open-case" data-case="${escapeHtml(row.case_id)}"><td><strong>${escapeHtml(FINDING_LABELS[row.type] || row.type)}</strong><small>${escapeHtml(row.case_id)}</small></td><td>${badge(row.severity)}</td><td>${escapeHtml(row.document)}</td><td>${escapeHtml(row.customer)}</td><td>${row.amount == null ? "—" : money(row.amount)}</td><td>${dateText(row.paid_at || row.issued_at)}</td><td>${operationalBadge(caseState(row, state.operationalStates))}</td><td>${escapeHtml(row.recommended_action)}</td></tr>`);
  return `<aside class="documentary-notice"><strong>Conciliación documental</strong><span>La conciliación disponible no corresponde a una conciliación bancaria. “Revisado” registra análisis humano, no conciliación bancaria.</span></aside><section class="section"><div class="section-title"><div><h3>Resumen de recaudación</h3><p>Aplicaciones y excepciones calculadas a la fecha de corte.</p></div></div>${metricCards(data.metrics || {})}</section><section class="section"><div class="section-title"><div><h3>Casos para trabajar</h3><p>${whole(filtered.length)} de ${whole(data.metrics?.exception_count)} casos visibles.</p></div></div>${exceptionFilterBar(currentCases)}${table(["Situación", "Prioridad", "Factura", "Cliente", "Importe", "Fecha", "Estado", "Siguiente acción"], rows, "No hay casos para los filtros seleccionados.")}</section>${technicalDetails(data)}`;
}

function renderEmptySelection(entity) {
  const label = entity === "customer" ? "cliente" : "factura";
  content.innerHTML = `<div class="empty large"><strong>Selecciona un ${label}</strong><span>Navega desde ${entity === "customer" ? "Prioridades" : "Cliente"} o utiliza la búsqueda superior.</span>${button(entity === "customer" ? "Ver prioridades" : "Ir a prioridades", "navigate", 'data-view="priorities"', "primary")}</div>`;
  setNotice(`Selecciona un ${label} para continuar.`);
}

function render(data) {
  currentData = data;
  if (!state.asOf && data.as_of_date) { state.asOf = data.as_of_date; renderControls(); persistState(); }
  setNotice(`Información calculada al ${dateText(data.as_of_date)}.`, "success");
  const renderers = { portfolio_snapshot: renderPortfolio, collection_priorities: renderPriorities,
    customer_snapshot: renderCustomer, invoice_trace: renderInvoice, reconciliation_exceptions: renderExceptions };
  content.innerHTML = (renderers[data.operation] || (() => technicalDetails(data)))(data);
}

function viewRequest() {
  const params = new URLSearchParams();
  if (state.asOf) params.set("as_of_date", state.asOf);
  if (state.view === "customer") params.set("id", state.customer);
  if (state.view === "invoice") params.set("id", state.invoice);
  if (["priorities", "exceptions"].includes(state.view)) params.set("limit", String(API_LIST_LIMIT));
  return `${API_BASE}/${state.view}?${params}`;
}

async function loadView(force = false) {
  if (state.view === "customer" && !state.customer) return renderEmptySelection("customer");
  if (state.view === "invoice" && !state.invoice) return renderEmptySelection("invoice");
  const path = viewRequest(); setNotice("Calculando resultado…");
  content.innerHTML = '<div class="loading"><span></span><span></span><span></span><p>Preparando evidencia determinística…</p></div>';
  try {
    let data = force ? null : cache.get(path);
    if (!data) { const response = await fetch(path); data = await response.json(); if (!response.ok) throw new Error(errorMessage(data, "No se pudo completar la consulta.")); cache.set(path, data); }
    render(data);
  } catch (error) {
    setNotice(error.message || "Ocurrió un error inesperado.", "error");
    content.innerHTML = `<div class="empty large"><strong>No se pudo cargar la vista</strong><span>${escapeHtml(error.message || "Ocurrió un error inesperado.")}</span>${button("Reintentar", "retry", "", "primary")}</div>`;
  }
}

function openDrawer(row) {
  if (!row) return;
  const stateValue = caseState(row, state.operationalStates);
  byId("drawer-backdrop").classList.remove("hidden"); const drawer = byId("case-drawer");
  drawer.setAttribute("aria-hidden", "false"); drawer.classList.add("open");
  drawer.innerHTML = `<div class="drawer-header"><div><span>${escapeHtml(row.case_id)}</span><h2 id="drawer-title">${escapeHtml(FINDING_LABELS[row.type] || row.type)}</h2></div>${button("Cerrar", "close-drawer", "", "text-button")}</div><div class="drawer-body"><div class="drawer-badges">${badge(row.severity)}${operationalBadge(stateValue)}</div><dl class="detail-grid"><div><dt>Cliente</dt><dd>${escapeHtml(row.customer)}</dd></div><div><dt>Factura</dt><dd>${escapeHtml(row.document)}</dd></div><div><dt>Pago</dt><dd>${row.payment ? `${money(row.payment.amount)} · ${dateText(row.payment.paid_at)}` : "No disponible"}</dd></div><div><dt>Saldo</dt><dd>${row.outstanding_balance == null ? "No disponible" : money(row.outstanding_balance)}</dd></div><div><dt>Nota de crédito</dt><dd>${row.credit_note ? escapeHtml(row.credit_note.document) : row.credit_notes?.length ? row.credit_notes.map((item) => escapeHtml(item.document)).join(", ") : "No aplica"}</dd></div><div><dt>Fecha de corte</dt><dd>${dateText(currentData?.as_of_date)}</dd></div></dl><section><h3>Motivo</h3><p>${escapeHtml(row.reason)}</p></section><section><h3>Evidencia</h3><p>${escapeHtml(row.evidence)}</p></section><section><h3>Siguiente acción recomendada</h3><p>${escapeHtml(row.recommended_action)}</p></section><div class="drawer-actions">${button("Marcar en revisión", "case-state", `data-case="${escapeHtml(row.case_id)}" data-state="EN_REVISION"`)}${button("Marcar revisado", "case-state", `data-case="${escapeHtml(row.case_id)}" data-state="REVISADO"`)}${button("Escalar para validación", "case-state", `data-case="${escapeHtml(row.case_id)}" data-state="ESCALAR"`)}${row.customer_available ? button("Ver cliente", "open-customer", `data-customer="${escapeHtml(row.customer)}"`) : ""}${row.invoice_available ? button("Ver factura", "open-invoice", `data-invoice="${escapeHtml(row.document)}"`, "primary") : ""}</div></div>`;
}

function closeDrawer() {
  byId("drawer-backdrop").classList.add("hidden"); const drawer = byId("case-drawer");
  drawer.classList.remove("open"); drawer.setAttribute("aria-hidden", "true");
}

function assistantCtas(data) {
  const ctas = [];
  for (const item of data.tool_results || []) {
    if (item.tool === "collection_priorities") ctas.push(["Ver prioridades", "priorities", {}]);
    if (item.tool === "reconciliation_exceptions") ctas.push(["Abrir conciliación documental", "exceptions", {}]);
    if (item.tool === "customer_snapshot" && item.arguments?.customer_id) ctas.push(["Abrir cliente", "customer", { customer: item.arguments.customer_id }]);
    if (item.tool === "invoice_trace" && item.arguments?.document) ctas.push(["Abrir factura", "invoice", { invoice: item.arguments.document }]);
    if (item.tool === "portfolio_snapshot") ctas.push(["Ver cartera", "portfolio", {}]);
  }
  return ctas.filter((item, index) => ctas.findIndex((other) => other[0] === item[0]) === index).slice(0, 3)
    .map(([label, view, context]) => button(label, "assistant-navigate", `data-view="${view}" data-context="${escapeHtml(JSON.stringify(context))}"`)).join("");
}

async function askAgent() {
  const question = byId("question").value.trim(); const shell = byId("answer-shell");
  const answer = byId("answer"); const aiBadge = byId("ai-badge"); const answerMode = byId("answer-mode");
  shell.classList.remove("hidden"); answer.classList.remove("error", "collapsed"); aiBadge.hidden = true; answerMode.textContent = "";
  if (!question) { answer.textContent = "Escribe una pregunta para el agente."; return; }
  answer.textContent = "Analizando consulta…";
  try {
    const response = await fetch(`${API_BASE}/query`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question, as_of_date: state.asOf || null }) });
    const data = await response.json(); if (!response.ok) throw new Error(errorMessage(data, "No se pudo completar la consulta con IA."));
    window.SoniaMarkdown.render(answer, data.answer || "La IA no devolvió una respuesta.");
    const aiGenerated = data.mode === "llm";
    aiBadge.hidden = !aiGenerated; answerMode.textContent = aiGenerated ? `${providerText[data.llm?.provider] || data.llm?.provider || "IA"} · ${data.llm?.model || "modelo configurado"} · cálculos determinísticos` : "Respuesta sustentada por las herramientas del agente.";
    byId("assistant-actions").innerHTML = assistantCtas(data); const toggle = byId("toggle-answer");
    const shouldCollapse = answer.scrollHeight > 280; answer.classList.toggle("collapsed", shouldCollapse);
    toggle.classList.toggle("hidden", !shouldCollapse); toggle.textContent = "Ver análisis completo"; toggle.setAttribute("aria-expanded", "false");
  } catch (error) { answer.classList.add("error"); answer.textContent = error.message || "No fue posible utilizar la IA."; byId("assistant-actions").innerHTML = ""; }
}

async function refreshStatus() {
  try {
    const response = await fetch(`${API_BASE}/status`); const data = await response.json(); if (!response.ok) throw new Error();
    const aiBadge = byId("ai-status"); aiBadge.textContent = data.llm_available ? "IA disponible" : "IA no disponible"; aiBadge.className = `status ${data.llm_available ? "ready" : "warn"}`;
    const dataBadge = byId("data-status"); dataBadge.textContent = data.dataset_configured ? "Fuente de Supervisor disponible" : "Supervisor aún no publicó datos"; dataBadge.className = `status ${data.dataset_configured ? "ready" : "warn"}`;
    return data.dataset_configured;
  } catch { byId("ai-status").textContent = "No se pudo verificar la IA"; byId("data-status").textContent = "No se pudo verificar el dataset"; return false; }
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action]"); if (!target) return; const action = target.dataset.action;
  if (action === "navigate") await navigate(target.dataset.view);
  if (action === "back") await goBack();
  if (action === "refresh") { state.asOf = byId("asof")?.value || ""; const entity = byId("entity")?.value.trim(); if (state.view === "customer") state.customer = entity; if (state.view === "invoice") state.invoice = entity; cache.clear(); persistState(); await loadView(true); }
  if (action === "retry") await loadView(true);
  if (action === "open-customer") { closeDrawer(); await navigate("customer", { customer: target.dataset.customer }); }
  if (action === "open-invoice") { closeDrawer(); await navigate("invoice", { invoice: target.dataset.invoice }); }
  if (action === "open-exceptions") await navigate("exceptions", { exceptionFilters: target.dataset.invoice ? { document: target.dataset.invoice } : {} });
  if (action === "overdue-cases") await navigate("priorities", { priorityFilters: { overdueOnly: true } });
  if (action === "partial-cases") await navigate("priorities", { priorityFilters: { partial: true } });
  if (action === "priority-filter") { const key = target.dataset.filter; const raw = target.dataset.value; const value = raw === "true" ? true : raw; state.priorityFilters[key] = state.priorityFilters[key] === value ? undefined : value; persistState(); render(currentData); }
  if (action === "clear-priority-filters") { state.priorityFilters = {}; persistState(); render(currentData); }
  if (action === "show-all-high") { state.priorityFilters = { priority: "HIGH" }; persistState(); render(currentData); }
  if (action === "toggle-managed") { const customer = target.dataset.customer; state.managedCustomers = state.managedCustomers.includes(customer) ? state.managedCustomers.filter((item) => item !== customer) : [...state.managedCustomers, customer]; persistState(); render(currentData); }
  if (action === "invoice-filter") { state.customerInvoiceFilter = target.dataset.value; persistState(); render(currentData); }
  if (action === "invoice-state") { state.invoiceStates[target.dataset.invoice] = target.dataset.state; persistState(); render(currentData); }
  if (action === "exception-filter") { const key = target.dataset.filter; const value = target.dataset.value; state.exceptionFilters[key] = state.exceptionFilters[key] === value ? undefined : value; persistState(); render(currentData); }
  if (action === "clear-exception-filters") { state.exceptionFilters = {}; persistState(); render(currentData); }
  if (action === "open-case") openDrawer(currentCases.find((row) => row.case_id === target.dataset.case));
  if (action === "close-drawer") closeDrawer();
  if (action === "case-state") { state.operationalStates[target.dataset.case] = target.dataset.state; persistState(); const row = currentCases.find((item) => item.case_id === target.dataset.case); render(currentData); openDrawer(row); }
  if (action === "assistant-navigate") await navigate(target.dataset.view, JSON.parse(target.dataset.context || "{}"));
});

document.addEventListener("change", (event) => {
  if (event.target.id === "priority-sort") { state.sortBy = event.target.value; persistState(); render(currentData); }
  if (event.target.id === "exception-state") { state.exceptionFilters.state = event.target.value || undefined; persistState(); render(currentData); }
  if (event.target.id === "exception-type") { state.exceptionFilters.type = event.target.value || undefined; persistState(); render(currentData); }
});

document.addEventListener("keydown", (event) => {
  const row = event.target.closest?.("tr[data-action]");
  if (row && ["Enter", " "].includes(event.key)) { event.preventDefault(); row.click(); }
  if (event.key === "Escape") closeDrawer();
});

document.querySelectorAll("[data-process]").forEach((item) => item.addEventListener("click", () => navigate(item.dataset.process === "revenue" ? "exceptions" : "portfolio")));
byId("ask").addEventListener("click", askAgent);
byId("question").addEventListener("keydown", (event) => { if (event.key === "Enter") askAgent(); });
byId("toggle-answer").addEventListener("click", (event) => { const expanded = event.currentTarget.getAttribute("aria-expanded") === "true"; byId("answer").classList.toggle("collapsed", expanded); event.currentTarget.setAttribute("aria-expanded", String(!expanded)); event.currentTarget.textContent = expanded ? "Ver análisis completo" : "Ver menos"; });
byId("drawer-backdrop").addEventListener("click", closeDrawer);

renderNavigation(); renderControls(); const datasetReady = await refreshStatus();
if (datasetReady) await loadView(); else setNotice("Supervisor todavía no ha publicado la fuente compartida.", "error");
