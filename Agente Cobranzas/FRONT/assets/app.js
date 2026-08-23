const API_BASE = "/api/collections";

const state = {
  view: "portfolio",
  asOf: "2026-08-07",
  customer: "CLIENT_00385",
  invoice: "S1AA-0052403449",
  limit: "10",
};

const byId = (id) => document.getElementById(id);
const content = byId("content");
const controls = byId("controls");
const feedback = byId("feedback");

const providerText = { "opencode-go": "OpenCode Go" };

const metricLabels = {
  total_billed: "Facturado",
  total_paid_linked: "Pagos aplicados a facturas",
  credit_notes_linked: "Notas de crédito aplicadas",
  outstanding_balance: "Saldo pendiente",
  overdue_balance: "Saldo vencido",
  collection_ratio: "Cobranza aplicada / facturación",
  collection_ratio_30_days: "Cobrado dentro de 30 días",
  average_collection_period_days: "Periodo medio de cobro",
  priority_score: "Índice de prioridad",
  exception_count: "Casos que requieren validación",
  payment_applications_analyzed: "Aplicaciones de pago analizadas",
  partial_payment_invoice_count: "Facturas con pago parcial",
};

const metricTips = {
  total_billed: "Importe total de las facturas analizadas.",
  total_paid_linked: "Incluye solo pagos vinculados con una factura del corte.",
  outstanding_balance: "Importe por cobrar después de pagos y notas de crédito.",
  overdue_balance: "Parte del saldo pendiente cuyo vencimiento ya pasó.",
  collection_ratio: "Pagos aplicados divididos entre el importe facturado.",
  collection_ratio_30_days: "Porcentaje cobrado hasta 30 días desde la emisión, usando solo facturas con una ventana completa al corte.",
  average_collection_period_days: "Promedio ponderado por importe entre emisión y aplicación del pago.",
  priority_score: "Índice de 0 a 100: alta desde 60 y media desde 30.",
  exception_count: "Casos para validar; no representan errores confirmados.",
  payment_applications_analyzed: "Pagos vinculados a facturas y observables a la fecha de corte.",
  partial_payment_invoice_count: "Facturas que recibieron pagos, pero aún mantienen saldo.",
};

const statusLabels = {
  priority: "Prioridad de gestión",
  collection_state: "Situación de cobranza",
  settlement: "Estado de pago",
  delinquency: "Situación de cobranza",
  reconciliation: "Aplicación de pagos",
};

const statusText = {
  HIGH: "Alta",
  MEDIUM: "Media",
  LOW: "Baja",
  PAGADA: "Pagada",
  PAGO_PARCIAL: "Pago parcial",
  PENDIENTE: "Pendiente de pago",
  SALDO_A_FAVOR: "Saldo a favor por validar",
  VENCIDA: "Vencida",
  CRITICA: "Vencida por más de 90 días",
  NO_VENCIDA: "Pendiente, aún no vencida",
  NO_APLICA: "Sin saldo pendiente",
  AL_DIA: "Al día al corte",
  CONCILIADA: "Pago aplicado completamente",
  PARCIALMENTE_CONCILIADA: "Pago aplicado parcialmente",
  PENDIENTE_DE_PAGO: "Sin pago aplicado",
  REQUIERE_REVISION: "Requiere validación",
};

const findingText = {
  UNMATCHED_PAYMENT_CUTOFF: "Pago sin factura dentro del corte analizado",
  OVERDUE_EXPOSURE: "Saldo vencido que requiere gestión",
  OPEN_BALANCE: "Factura con saldo pendiente",
  OVERAPPLICATION: "Saldo a favor por validar",
  TEMPORAL_ANOMALY: "Fecha de pago por validar",
  PAYMENT_OUTSIDE_INVOICE_CUTOFF: "Pago sin factura dentro del corte",
  PAYMENT_BEFORE_ISSUANCE: "Fecha de pago por validar",
  PAYMENT_LINK_MISMATCH: "Pago asociado a otro cliente o cuenta",
  CREDIT_NOTE_OUTSIDE_INVOICE_CUTOFF: "Nota de crédito sin factura dentro del corte",
  DOCUMENT_SETTLED: "Documento sin incidencias detectadas",
  SCORING_RULE: "Criterios de priorización aplicados",
};

const actionText = {
  review_collection_priorities: "Revisar clientes prioritarios",
  review_unmatched_payments: "Validar pagos fuera del corte",
  contact_customer: "Contactar al cliente",
  monitor: "Mantener seguimiento",
  review_overapplication: "Validar saldo a favor",
  start_collection: "Iniciar gestión de cobranza",
  monitor_due_date: "Dar seguimiento al vencimiento",
  close_case: "No requiere gestión adicional",
  assign_collection_queue: "Asignar clientes prioritarios a gestión",
  review_exceptions: "Revisar casos de aplicación",
};

const bucketText = {
  NO_VENCIDA: "Aún no vencida",
  "1_30": "De 1 a 30 días vencida",
  "31_60": "De 31 a 60 días vencida",
  "61_90": "De 61 a 90 días vencida",
  "90_PLUS": "Más de 90 días vencida",
  SIN_FECHA_VENCIMIENTO: "Sin fecha de vencimiento",
};

function escapeHtml(value) {
  return String(value ?? "—")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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

function percent(value) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function whole(value) {
  return typeof value === "number" ? new Intl.NumberFormat("es-PE").format(value) : "—";
}

function badge(value) {
  return `<span class="badge ${escapeHtml(value)}">${escapeHtml(statusText[value] || value)}</span>`;
}

function errorMessage(payload, fallback) {
  const detail = payload?.detail ?? payload?.error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail?.errors)) return detail.errors.join(" ");
  if (Array.isArray(payload?.errors)) return payload.errors.join(" ");
  return fallback;
}

function setNotice(message, type = "") {
  feedback.className = `notice ${type}`.trim();
  feedback.textContent = message;
}

function renderControls() {
  let form = `
    <div class="field">
      <label for="asof">Fecha de corte</label>
      <input id="asof" type="date" value="${escapeHtml(state.asOf)}">
      <span class="help">Los resultados no se actualizan en tiempo real.</span>
    </div>`;

  if (state.view === "customer") {
    form += `
      <div class="field">
        <label for="entity">Código de cliente</label>
        <input id="entity" value="${escapeHtml(state.customer)}" placeholder="Ej.: CLIENT_00385">
      </div>`;
  }
  if (state.view === "invoice") {
    form += `
      <div class="field">
        <label for="entity">N.° de factura</label>
        <input id="entity" value="${escapeHtml(state.invoice)}" placeholder="Ej.: S1AA-0052403449">
      </div>`;
  }
  if (["priorities", "exceptions"].includes(state.view)) {
    form += `
      <div class="field">
        <label for="limit">Cantidad de casos</label>
        <input id="limit" type="number" min="1" max="50" value="${escapeHtml(state.limit)}">
      </div>`;
  }

  controls.innerHTML = `<div class="controls">${form}<button class="primary" id="run" type="button">Consultar</button></div>`;
  byId("run").addEventListener("click", loadView);
}

function metricCard(key, value) {
  let text = money(value);
  if (key === "priority_score") text = `${Number(value).toFixed(1)} / 100`;
  if (["collection_ratio", "collection_ratio_30_days"].includes(key)) text = percent(value);
  if (key === "average_collection_period_days") text = value == null ? "No disponible" : `${Number(value).toFixed(1)} días`;
  if (["exception_count", "payment_applications_analyzed", "partial_payment_invoice_count"].includes(key)) text = whole(value);
  return `
    <div class="card" title="${escapeHtml(metricTips[key] || "")}">
      <span>${escapeHtml(metricLabels[key] || key)}</span>
      <strong>${text}</strong>
    </div>`;
}

function metricCards(metrics) {
  const preferred = [
    "total_billed",
    "total_paid_linked",
    "outstanding_balance",
    "overdue_balance",
    "collection_ratio",
    "collection_ratio_30_days",
    "average_collection_period_days",
    "priority_score",
    "payment_applications_analyzed",
    "partial_payment_invoice_count",
    "exception_count",
  ];
  return `<div class="cards">${preferred.filter((key) => key in metrics).map((key) => metricCard(key, metrics[key])).join("")}</div>`;
}

function table(headers, rows) {
  if (!rows.length) return '<div class="empty">No hay registros para mostrar.</div>';
  return `
    <div class="table-wrap">
      <table>
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>`;
}

function renderAging(rows) {
  return `
    <section class="section">
      <h2>Antigüedad de la deuda</h2>
      <p class="section-intro">Agrupa el saldo pendiente según los días transcurridos desde el vencimiento.</p>
      ${table(
        ["Tramo de vencimiento", "Facturas", "Saldo pendiente"],
        rows.map((row) => [
          escapeHtml(bucketText[row.bucket] || row.bucket),
          whole(row.documents),
          money(row.outstanding_balance),
        ]),
      )}
    </section>`;
}

function renderFindings(rows) {
  return `
    <section class="section">
      <h2>Situaciones identificadas</h2>
      <p class="section-intro">Hallazgos respaldados por el corte; no reemplazan la validación operativa.</p>
      ${table(
        ["Situación", "Nivel", "Qué significa", "Importe", "Casos"],
        rows.map((row) => [
          escapeHtml(findingText[row.type] || row.type),
          badge(row.severity),
          escapeHtml(row.message),
          row.amount == null ? "—" : money(row.amount),
          row.count == null ? "—" : whole(row.count),
        ]),
      )}
    </section>`;
}

function renderActions(rows) {
  return `
    <section class="section">
      <h2>Siguientes acciones recomendadas</h2>
      <div class="action-list">
        ${rows.map((row) => `
          <div class="action">
            <strong>${escapeHtml(actionText[row.action] || row.action)}</strong>
            <span>${escapeHtml(row.reason || "")}</span>
            ${row.priority ? `<br>${badge(row.priority)}` : ""}
          </div>`).join("")}
      </div>
    </section>`;
}

function renderKpiDefinitions(kpis) {
  const rows = Object.values(kpis || {}).filter((item) => item?.definition);
  if (!rows.length) return "";
  return `
    <details>
      <summary>Cómo se calculan los indicadores</summary>
      <ul>${rows.map((item) => `<li>${escapeHtml(item.definition)}</li>`).join("")}</ul>
    </details>`;
}

function renderCustomerInvoices(rows) {
  const open = rows.filter((row) => row.outstanding_balance > 0);
  return `
    <section class="section">
      <h2>Facturas por gestionar</h2>
      <p class="section-intro">Se muestran únicamente documentos con saldo pendiente.</p>
      ${table(
        ["Factura", "Vencimiento", "Días de atraso", "Facturado", "Pagos", "Saldo", "Estado", "Aplicación"],
        open.map((row) => [
          escapeHtml(row.document),
          dateText(row.due_at),
          whole(row.days_past_due),
          money(row.invoice_total),
          money(row.paid),
          money(row.outstanding_balance),
          badge(row.settlement_state),
          badge(row.reconciliation_state),
        ]),
      )}
    </section>`;
}

function renderInvoiceDetail(row) {
  const payments = row.payments || [];
  const credits = row.credit_note_documents || [];
  const summary = table(
    ["Cliente", "Cuenta", "Emisión", "Vencimiento", "Atraso", "Facturado", "Notas de crédito", "Pagos", "Saldo"],
    [[
      escapeHtml(row.customer),
      escapeHtml(row.account_code),
      dateText(row.issued_at),
      dateText(row.due_at),
      whole(row.days_past_due),
      money(row.invoice_total),
      money(row.credit_notes),
      money(row.paid),
      money(row.outstanding_balance),
    ]],
  );
  const paymentTable = table(
    ["Fecha de pago", "Importe aplicado", "Cuenta"],
    payments.map((payment) => [dateText(payment.paid_at), money(payment.amount), escapeHtml(payment.account_code)]),
  );
  const creditTable = credits.length
    ? table(
        ["Documento", "Fecha de emisión", "Importe"],
        credits.map((credit) => [escapeHtml(credit.document), dateText(credit.issued_at), money(credit.amount)]),
      )
    : "";
  return `
    <section class="section"><h2>Resumen de la factura</h2>${summary}</section>
    <section class="section"><h2>Pagos aplicados a esta factura</h2>${paymentTable}</section>
    ${creditTable ? `<section class="section"><h2>Notas de crédito aplicadas</h2>${creditTable}</section>` : ""}`;
}

function renderPriorities(rows, data) {
  return `
    <section class="section">
      <h2>Clientes a priorizar</h2>
      <p class="section-intro">${whole(data.metrics.customers_ranked)} clientes tienen saldo pendiente.</p>
      ${table(
        ["Posición", "Cliente", "Saldo", "Vencido", "Mayor atraso", "% vencido", "Índice / 100", "Prioridad"],
        rows.map((row, index) => [
          whole(index + 1),
          escapeHtml(row.customer),
          money(row.outstanding_balance),
          money(row.overdue_balance),
          whole(row.max_days_past_due),
          percent(row.overdue_share),
          `${Number(row.priority_score).toFixed(1)} / 100`,
          badge(row.priority),
        ]),
      )}
    </section>`;
}

function renderExceptions(rows, data) {
  return `
    <section class="section">
      <h2>Casos para validar</h2>
      <p class="section-intro">Se identificaron ${whole(data.metrics.exception_count)} casos; no son errores confirmados.</p>
      ${table(
        ["Situación", "Prioridad", "Factura", "Cliente", "Importe", "Fecha", "Siguiente acción"],
        rows.map((row) => [
          escapeHtml(findingText[row.type] || row.type),
          badge(row.severity),
          escapeHtml(row.document),
          escapeHtml(row.customer),
          row.amount == null ? "—" : money(row.amount),
          row.paid_at || row.issued_at ? dateText(row.paid_at || row.issued_at) : "—",
          escapeHtml(row.recommended_action),
        ]),
      )}
    </section>`;
}

function statusLine(items) {
  const visible = Object.entries(items).filter(([key]) => statusLabels[key]);
  if (!visible.length) return "";
  return `<div class="status-line"><span class="status-label">Estado:</span>${visible.map(([key, value]) => `<span>${escapeHtml(statusLabels[key])}: ${badge(value)}</span>`).join("<span>·</span>")}</div>`;
}

function narrative(data) {
  const metrics = data.metrics || {};
  const cut = dateText(data.as_of_date);
  if (data.operation === "portfolio_snapshot") return `Al ${cut}, la cartera mantiene ${money(metrics.outstanding_balance)} pendiente; ${money(metrics.overdue_balance)} ya está vencido.`;
  if (data.operation === "customer_snapshot") return metrics.overdue_balance > 0 ? `Al ${cut}, este cliente tiene ${money(metrics.overdue_balance)} vencido.` : `Al ${cut}, este cliente no tiene saldo vencido.`;
  if (data.operation === "invoice_trace") return `Al ${cut}, esta factura conserva ${money(metrics.outstanding_balance)} pendiente.`;
  if (data.operation === "collection_priorities") return "El ranking considera importe vencido, atraso, porcentaje vencido y concentración de deuda.";
  return "La conciliación disponible es documental; no corresponde a una conciliación bancaria.";
}

function render(data) {
  setNotice(`Información calculada al ${dateText(data.as_of_date)}.`);
  let html = `<p class="narrative">${escapeHtml(narrative(data))}</p>${metricCards(data.metrics || {})}${statusLine(data.status || {})}`;
  if (["portfolio_snapshot", "customer_snapshot"].includes(data.operation) && data.aging?.length) html += renderAging(data.aging);
  if (["portfolio_snapshot", "customer_snapshot", "invoice_trace"].includes(data.operation) && data.findings?.length) html += renderFindings(data.findings);
  if (data.operation === "customer_snapshot") html += renderCustomerInvoices(data.evidence || []);
  if (data.operation === "invoice_trace") html += renderInvoiceDetail(data.evidence?.[0] || {});
  if (data.operation === "collection_priorities") {
    html += renderPriorities(data.evidence || [], data);
    html += "<details><summary>Cómo se calcula la prioridad</summary><p>Índice de 0 a 100: alta desde 60, media desde 30 y baja por debajo de 30.</p></details>";
  }
  if (data.operation === "reconciliation_exceptions") html += renderExceptions(data.evidence || [], data);
  if (data.recommended_actions?.length) html += renderActions(data.recommended_actions);
  html += renderKpiDefinitions(data.kpis);
  html += `<details><summary>Detalle técnico e integración (JSON)</summary><pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre></details>`;
  content.innerHTML = html;
}

async function loadView() {
  state.asOf = byId("asof").value;
  let path = `${API_BASE}/${state.view}?as_of_date=${encodeURIComponent(state.asOf)}`;
  const entity = byId("entity");
  const limit = byId("limit");
  if (entity) {
    const value = entity.value.trim();
    if (state.view === "customer") state.customer = value;
    else state.invoice = value;
    path += `&id=${encodeURIComponent(value)}`;
  }
  if (limit) {
    state.limit = limit.value;
    path += `&limit=${encodeURIComponent(limit.value)}`;
  }

  setNotice("Calculando resultado…");
  content.innerHTML = "";
  try {
    const response = await fetch(path);
    const data = await response.json();
    if (!response.ok) throw new Error(errorMessage(data, "No se pudo completar la consulta."));
    render(data);
  } catch (error) {
    setNotice(error.message || "Ocurrió un error inesperado.", "error");
  }
}

async function refreshStatus() {
  try {
    const response = await fetch(`${API_BASE}/status`);
    const data = await response.json();
    if (!response.ok) throw new Error();
    const aiBadge = byId("ai-status");
    aiBadge.textContent = data.llm_available ? "Consultas con IA disponibles" : "Consultas con IA no disponibles";
    aiBadge.title = data.llm_available
      ? `Proveedor: ${providerText[data.llm?.provider] || data.llm?.provider || "OpenCode Go"} · Modelo: ${data.llm?.model || data.model}`
      : "La configuración debe realizarla un administrador.";
    aiBadge.className = `status ${data.llm_available ? "ready" : "warn"}`;
    const dataBadge = byId("data-status");
    dataBadge.textContent = data.dataset_configured
      ? "Fuente de Supervisor disponible"
      : "Supervisor aún no publicó datos";
    dataBadge.className = `status ${data.dataset_configured ? "ready" : "warn"}`;
    return data.dataset_configured;
  } catch {
    byId("ai-status").textContent = "No se pudo verificar la IA";
    byId("data-status").textContent = "No se pudo verificar el dataset";
    return false;
  }
}

async function askAgent() {
  const question = byId("question").value.trim();
  const answer = byId("answer");
  const aiBadge = byId("ai-badge");
  const answerMode = byId("answer-mode");
  answer.classList.remove("hidden", "error");
  aiBadge.hidden = true;
  answerMode.textContent = "";
  if (!question) {
    answer.textContent = "Escribe una pregunta para el agente.";
    return;
  }
  answer.textContent = "Analizando consulta…";
  try {
    const response = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, as_of_date: state.asOf }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(errorMessage(data, "No se pudo completar la consulta con IA."));
    window.SoniaMarkdown.render(answer, data.answer || "La IA no devolvió una respuesta.");
    const aiGenerated = data.mode === "llm";
    aiBadge.hidden = !aiGenerated;
    answerMode.textContent = aiGenerated
      ? `${providerText[data.llm?.provider] || data.llm?.provider || "IA"} · ${data.llm?.model || "modelo configurado"} · cálculos determinísticos`
      : "Respuesta sustentada por las herramientas del agente.";
  } catch (error) {
    answer.classList.add("error");
    answer.textContent = error.message || "No fue posible utilizar la IA.";
    aiBadge.hidden = true;
    answerMode.textContent = "";
  }
}

document.querySelectorAll(".nav button").forEach((button) => {
  button.addEventListener("click", () => {
    state.view = button.dataset.view;
    document.querySelectorAll(".nav button").forEach((item) => item.classList.toggle("active", item === button));
    renderControls();
    loadView();
  });
});

byId("ask").addEventListener("click", askAgent);

renderControls();
const datasetReady = await refreshStatus();
if (datasetReady) await loadView();
else setNotice("Supervisor todavía no ha publicado la fuente compartida.", "error");
