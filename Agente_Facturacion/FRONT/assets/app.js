"use strict";

const demo = window.SONIA_BILLING_UI.demo;
const state = {
  view: "summary", datasetId: "default", asOf: "", customer: demo.customer,
  account: demo.account, invoice: demo.arithmeticInvoice, threshold: "", question: "¿Qué debería revisar hoy?",
  context: {}, datasetStatus: null, workQueue: null, queueFilter: "all"
};
const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? "—").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const number = value => typeof value === "number" ? new Intl.NumberFormat("es-PE").format(value) : "—";
const money = value => typeof value === "number" ? new Intl.NumberFormat("es-PE", {style:"currency", currency:"PEN"}).format(value) : "—";
const percent = value => typeof value === "number" ? new Intl.NumberFormat("es-PE", {style:"percent", maximumFractionDigits:1}).format(value) : "—";
const displayDate = value => value ? String(value).split("-").reverse().join("/") : "—";
const plantStatusLabel = value => ({Active:"Activa",Activo:"Activa",Inactive:"Inactiva",Inactivo:"Inactiva"}[value] || value);
const apiBase = String(window.SONIA_BILLING_UI.apiBase || "/api").replace(/\/$/, "");

function moneyByCurrency(value, currency) {
  if (typeof value !== "number") return "No cuantificable";
  if (!currency) return `${new Intl.NumberFormat("es-PE", {minimumFractionDigits:2, maximumFractionDigits:2}).format(value)} · moneda no informada`;
  try {
    return new Intl.NumberFormat("es-PE", {style:"currency", currency}).format(value);
  } catch (_error) {
    return `${currency} ${new Intl.NumberFormat("es-PE", {minimumFractionDigits:2, maximumFractionDigits:2}).format(value)}`;
  }
}

function caseAmount(item) {
  if (typeof item.amount === "number") return moneyByCurrency(item.amount, item.currency);
  const amounts = item.amounts_by_currency || [];
  return amounts.length ? amounts.map(entry => moneyByCurrency(entry.amount, entry.currency)).join(" + ") : "No cuantificable";
}

function apiEndpoint(path) {
  if (path === apiBase || path.startsWith(apiBase + "/") || path.startsWith(apiBase + "?")) return path;
  return path.startsWith("/api/") ? `${apiBase}${path.slice(4)}` : path;
}

function apiUrl(path, params = {}) {
  const url = new URL(apiEndpoint(path), window.location.origin);
  if (state.datasetId) url.searchParams.set("dataset_id", state.datasetId);
  Object.entries(params).forEach(([key,value]) => { if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value); });
  return url.pathname + url.search;
}

function apiError(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (payload?.detail?.message) {
    const missing = payload.detail.missing_columns?.length ? ` Faltan: ${payload.detail.missing_columns.join(", ")}.` : "";
    const source = payload.detail.source ? ` Fuente: ${payload.detail.source}.` : "";
    return `${payload.detail.message}${source}${missing}`;
  }
  if (Array.isArray(payload?.detail)) return payload.detail.map(item => item.msg).join("; ");
  return payload?.error || fallback;
}

async function requestJson(url, options) {
  const response = await fetch(apiEndpoint(url), options);
  const payload = response.status === 204 ? {} : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(apiError(payload, "No se pudo completar la solicitud."));
  return payload;
}

function sourceLabel(key) {
  return {customers:"Clientes", fixed_plant:"Planta fija", mobile_plant:"Planta móvil", invoices:"Facturas", credit_notes:"Notas de crédito"}[key] || key;
}

async function refreshDatasetStatus(datasetId = state.datasetId) {
  state.datasetId = datasetId;
  const status = await requestJson(apiUrl("/api/status"));
  state.datasetStatus = status;
  state.context = {};
  if (status.status === "dataset_not_configured" || status.dataset_configured === false) {
    state.asOf = "";
    state.datasetId = "default";
    $("#cutoff").textContent = "Corte —";
    $("#mode").textContent = status.llm_available ? "Modo asistido · tools verificables" : "Modo local determinístico";
    $("#dataset-summary").textContent = "Supervisor todavía no ha publicado una fuente de datos.";
    $("#source-counts").innerHTML = ["customers", "fixed_plant", "mobile_plant", "invoices", "credit_notes"]
      .map(key => '<div class="source-chip"><span>' + escapeHtml(sourceLabel(key)) + '</span><strong>Pendiente</strong></div>').join("");
    return false;
  }
  state.asOf = status.max_as_of_date;
  state.datasetId = status.dataset_id;
  $("#cutoff").textContent = `Corte ${displayDate(status.max_as_of_date)}`;
  $("#mode").textContent = status.llm_available ? "Modo asistido · tools verificables" : "Modo local determinístico";
  $("#dataset-summary").textContent = `${status.origin} · LISTO PARA ANALIZAR`;
  $("#source-counts").innerHTML = status.sources.map(item => `<div class="source-chip"><span>${escapeHtml(sourceLabel(item.key))} · ✓ válido</span><strong>${number(item.records)}</strong></div>`).join("");
  return true;
}

function showDatasetNotConfigured() {
  $("#feedback").className = "notice warn";
  $("#feedback").textContent = "Supervisor todavía no ha publicado la fuente compartida.";
  $("#content").innerHTML = '<div class="empty">Fuentes requeridas: Clientes, Planta fija, Planta móvil, Facturas y Notas de crédito. No se requiere la tabla Pagos.</div>';
}

function commonAsOf() {
  return `<div class="field"><label for="asof">Fecha de corte</label><input id="asof" type="date" value="${escapeHtml(state.asOf)}"></div>`;
}

function controls() {
  let html = commonAsOf();
  let suggestions = [];
  if (state.view === "customer") {
    html += `<div class="field"><label for="customer">Cliente</label><input id="customer" value="${escapeHtml(state.customer)}"></div><div class="field"><label for="account">Cuenta opcional</label><input id="account" value="${escapeHtml(state.account)}"></div>`;
    suggestions = [["Caso de quiebre", demo.customer, demo.account]];
  } else if (state.view === "invoice") {
    html += `<div class="field"><label for="invoice">Documento fiscal</label><input id="invoice" value="${escapeHtml(state.invoice)}"></div>`;
    suggestions = [["Diferencia aritmética",demo.arithmeticInvoice],["Moneda no informada",demo.missingCurrencyInvoice],["Importe cero",demo.zeroInvoice],["NC material",demo.creditInvoice]];
  } else if (state.view === "gaps") {
    html += `<div class="field"><label for="customer">Cliente opcional</label><input id="customer" value="${escapeHtml(state.customer)}"></div><div class="field"><label for="account">Cuenta opcional</label><input id="account" value="${escapeHtml(state.account)}"></div>`;
    suggestions = [["Quiebre documental demo", demo.customer, demo.account]];
  } else if (state.view === "notes") {
    html += `<div class="field"><label for="invoice">Factura opcional</label><input id="invoice" value="${escapeHtml(state.invoice === demo.arithmeticInvoice ? demo.creditInvoice : state.invoice)}"></div><div class="field"><label for="threshold">Umbral opcional</label><input id="threshold" inputmode="decimal" placeholder="Criterio del backend" value="${escapeHtml(state.threshold)}"></div>`;
    suggestions = [["Ajuste material demo",demo.creditInvoice]];
  } else if (state.view === "agent") {
    html += `<div class="field" style="grid-column:span 2"><label for="question">Consulta en lenguaje natural</label><input id="question" value="${escapeHtml(state.question)}"></div>`;
    suggestions = [["¿Qué debería revisar hoy?"],[`Revisa la factura ${demo.arithmeticInvoice}`],[`Analiza ${demo.customer}`],["¿Cuánto debe CLIENT_00434?"]];
  }
  html += `<button id="run" class="button" type="button">${state.view === "agent" ? "Consultar" : "Analizar evidencia"}</button>`;
  $("#controls").innerHTML = html;
  $("#suggestions").innerHTML = suggestions.map((item,index) => `<button class="suggestion" data-example="${index}">${escapeHtml(item[0])}</button>`).join("");
  $("#run").onclick = loadView;
  document.querySelectorAll("[data-example]").forEach(button => button.onclick = () => {
    const example = suggestions[Number(button.dataset.example)];
    if (state.view === "agent") { state.question = example[0]; $("#question").value = example[0]; }
    if (["customer","gaps"].includes(state.view)) { state.customer = example[1]; state.account = example[2]; $("#customer").value=example[1]; $("#account").value=example[2]; }
    if (["invoice","notes"].includes(state.view)) { state.invoice = example[1]; $("#invoice").value=example[1]; }
    loadView();
  });
}

function evidenceDetails(finding, payload) {
  const refs = new Set(finding.evidence_refs || []);
  const evidence = (payload.evidence || []).filter(item => refs.has(item.id));
  return `<details><summary>Ver evidencia</summary><p><strong>Regla:</strong> ${escapeHtml(finding.validation_rule || finding.expected_rule)}</p><p><strong>Siguiente validación:</strong> ${escapeHtml(finding.recommended_validation)}</p><pre>${escapeHtml(JSON.stringify({technical_code:finding.type, observed_value:finding.observed_value, evidence}, null, 2))}</pre></details>`;
}

function findings(payload, presentation) {
  const presented = presentation?.findings || [];
  if (!presented.length) return `<div class="empty">No se detectaron hallazgos en el alcance documental consultado.</div>`;
  return presented.map(item => `<article class="finding ${escapeHtml(item.severity)}"><div class="badges"><span class="badge ${escapeHtml(item.severity)}">${escapeHtml(item.severity_label)}</span><span class="badge">${escapeHtml(item.rule_category_label)}</span></div><h3>${escapeHtml(item.business_label)}</h3><p>${escapeHtml(item.message)}</p>${evidenceDetails(item,payload)}</article>`).join("");
}

function technical(payload) {
  return `<details><summary>Ver trazabilidad técnica · AgentResponse v1.0</summary><pre>${escapeHtml(JSON.stringify(payload,null,2))}</pre></details>`;
}

function csvCell(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function downloadWorkQueue(cases) {
  const headers = ["Prioridad", "Categoría de riesgo", "Cliente", "Cuenta", "Factura", "Periodo", "Hallazgo", "Monto involucrado", "Moneda", "Evidencia resumida", "Acción recomendada"];
  const rows = cases.map(item => [
    item.priority, item.risk_category, item.customer, item.account, item.invoice_id,
    item.period, item.title, typeof item.amount === "number" ? item.amount.toLocaleString("es-PE", {useGrouping:false, minimumFractionDigits:2, maximumFractionDigits:2}) : "",
    item.currency, item.evidence_summary, item.recommended_action
  ]);
  const csv = "\uFEFF" + [headers, ...rows].map(row => row.map(csvCell).join(";")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], {type:"text/csv;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = `casos_facturacion_${state.asOf || "corte"}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function selectView(view) {
  state.view = view;
  document.querySelectorAll(".nav button").forEach(item => item.classList.toggle("active", item.dataset.view === view));
  controls();
  loadView();
}

function openCase(item) {
  const target = item.drilldown || {};
  if (target.customer_id) state.customer = target.customer_id;
  if (target.account_id) state.account = target.account_id;
  if (target.invoice_id) state.invoice = target.invoice_id;
  selectView(target.view || "invoice");
}

function workQueueRows(cases) {
  if (!cases.length) return `<div class="empty">No hay casos accionables para el filtro seleccionado.</div>`;
  return `<div class="table-wrap work-queue-table"><table><thead><tr><th>Prioridad</th><th>Categoría de riesgo</th><th>Cliente</th><th>Cuenta</th><th>Factura / periodo</th><th>Qué detectó COBI</th><th>Monto involucrado</th><th>Acción recomendada</th></tr></thead><tbody>${cases.map(item => `<tr>
    <td><span class="badge ${escapeHtml(item.priority)}">${escapeHtml({HIGH:"Alta",MEDIUM:"Media",LOW:"Baja"}[item.priority] || item.priority)}</span></td>
    <td>${escapeHtml(item.risk_category)}</td><td>${escapeHtml(item.customer)}</td><td>${escapeHtml(item.account)}</td>
    <td><strong>${escapeHtml(item.invoice_id || item.period)}</strong>${item.invoice_id && item.period ? `<small>${escapeHtml(item.period)}</small>` : ""}</td>
    <td><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.evidence_summary)}</p></td>
    <td><strong>${escapeHtml(caseAmount(item))}</strong><small>${escapeHtml(item.amount_basis)}</small></td>
    <td><p>${escapeHtml(item.recommended_action)}</p><button class="button secondary case-drilldown" type="button" data-case-id="${escapeHtml(item.case_id)}">Investigar caso</button></td>
  </tr>`).join("")}</tbody></table></div>`;
}

function renderWorkQueue(queue, filter = state.queueFilter) {
  state.workQueue = queue;
  state.queueFilter = filter;
  const summary = queue.summary || {};
  const cases = filter === "all" ? queue.cases : queue.cases.filter(item => item.risk_category === filter);
  const amounts = summary.quantifiable_amounts_by_currency || [];
  const categoryCounts = summary.risk_category_counts || {};
  const categories = ["Riesgo de ingreso", "Ajustes post-emisión", "Calidad documental"];
  const amountHtml = amounts.length ? amounts.map(item => `<span>${escapeHtml(moneyByCurrency(item.amount, item.currency))}</span>`).join("") : "<span>Sin monto agregable</span>";
  const technicalCases = cases.map(item => `<details><summary>${escapeHtml(item.case_id)} · Ver trazabilidad técnica</summary><pre>${escapeHtml(JSON.stringify(item.technical_trace, null, 2))}</pre></details>`).join("");
  $("#content").innerHTML = `<div class="narrative"><strong>Bandeja automática de revisión.</strong> SON-IA agrupó las señales existentes en casos únicos y priorizados. Ningún monto representa pérdida confirmada.</div>
  <section class="section"><h2>Estado operativo</h2><div class="kpis work-queue-kpis">
    <div class="kpi"><span>Facturas analizadas</span><strong>${number(summary.invoice_documents)}</strong></div>
    <div class="kpi"><span>Facturas sin observaciones documentales detectadas</span><strong>${number(summary.invoices_without_documentary_findings)}</strong></div>
    <div class="kpi attention"><span>Casos que requieren atención</span><strong>${number(summary.cases_requiring_attention)}</strong></div>
    <div class="kpi"><span>Monto cuantificable asociado</span><strong class="amount-stack">${amountHtml}</strong></div>
  </div><p class="scope-note">“Sin observaciones detectadas” significa que la factura pasó las validaciones disponibles con las fuentes conectadas. No valida PxQ contractual.</p></section>
  <section class="section"><div class="section-heading"><div><h2>Resumen por riesgo</h2><p>Filtra la bandeja sin modificar la priorización del backend.</p></div><button id="download-queue" class="button secondary" type="button">Descargar casos que requieren atención (.csv)</button></div>
    <div class="risk-grid"><button type="button" class="risk-card ${filter === "all" ? "active" : ""}" data-queue-filter="all"><span>Todos los casos</span><strong>${number(summary.cases_requiring_attention)}</strong></button>${categories.map(category => `<button type="button" class="risk-card ${filter === category ? "active" : ""}" data-queue-filter="${escapeHtml(category)}"><span>${escapeHtml(category)}</span><strong>${number(categoryCounts[category] || 0)}</strong></button>`).join("")}</div>
  </section>
  <section class="section"><h2>Casos que requieren atención</h2><p>${number(cases.length)} casos visibles · ordenados por prioridad y monto comparable dentro de cada moneda.</p>${workQueueRows(cases)}</section>
  <section class="section queue-trace"><h2>Trazabilidad técnica</h2><p>Detalle auditable separado de la bandeja operativa.</p>${technicalCases || `<div class="empty">Sin trazas para el filtro seleccionado.</div>`}</section>`;
  document.querySelectorAll("[data-queue-filter]").forEach(button => button.onclick = () => renderWorkQueue(queue, button.dataset.queueFilter));
  document.querySelectorAll("[data-case-id]").forEach(button => button.onclick = () => openCase(queue.cases.find(item => item.case_id === button.dataset.caseId)));
  $("#download-queue").onclick = () => downloadWorkQueue(queue.cases);
}

function renderCustomer(payload, presentation) {
  const m=payload.metrics||{}, evidence=payload.evidence||[];
  const invoices=evidence.filter(item=>item.type==="invoice").map(item=>item.value);
  const plant=evidence.filter(item=>item.type==="plant");
  return `<div class="narrative">${escapeHtml(presentation.narrative)}</div><section class="section"><h2>Billing 360</h2><div class="kpis"><div class="kpi"><span>Cuentas en alcance</span><strong>${number(m.account_count)}</strong></div><div class="kpi"><span>Facturas</span><strong>${number(m.invoice_count)}</strong></div><div class="kpi"><span>Notas de crédito</span><strong>${number(m.credit_note_count)}</strong></div><div class="kpi"><span>Hallazgos</span><strong>${number((payload.findings||[]).length)}</strong></div></div></section>
  <section class="section"><h2>Cuentas y planta</h2>${plant.length ? plant.map(item=>`<div class="account"><strong>${escapeHtml(item.value?.account || item.id.replace("plant:",""))}</strong><p>Presencia en planta confirmada en el extracto. Los estados, planes y filas fuente están disponibles en evidencia.</p><details><summary>Ver detalle de planta</summary><pre>${escapeHtml(JSON.stringify(item.value,null,2))}</pre></details></div>`).join("") : `<div class="empty">No se encontró planta enlazada; esto no constituye por sí solo una incidencia.</div>`}</section>
  <section class="section"><h2>Documentos</h2>${invoices.length ? `<div class="table-wrap"><table><thead><tr><th>Factura</th><th>Cuenta</th><th>Fecha</th><th>Sistema</th><th>Total</th></tr></thead><tbody>${invoices.map(item=>`<tr><td>${escapeHtml(item.document)}</td><td>${escapeHtml(item.account)}</td><td>${displayDate(item.issued_at)}</td><td>${escapeHtml(item.system)}</td><td>${money(item.total)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">Sin evidencia de factura en el extracto. No equivale a “no facturado”.</div>`}</section><section class="section"><h2>Hallazgos y siguientes validaciones</h2>${findings(payload,presentation)}</section>${technical(payload)}`;
}

function renderInvoice(payload,presentation) {
  const m=payload.metrics||{}, invoice=(payload.evidence||[]).find(item=>item.type==="invoice")?.value||{};
  const notes=(payload.evidence||[]).filter(item=>item.type==="credit_note").map(item=>item.value);
  return `<div class="narrative">${escapeHtml(presentation.narrative)}</div><section class="section"><h2>${escapeHtml(invoice.document || payload.entity?.id)}</h2><p>${escapeHtml(invoice.customer)} · Cuenta ${escapeHtml(invoice.account)} · ${escapeHtml(invoice.system)} / ${escapeHtml(invoice.source)} · Emisión ${displayDate(invoice.issued_at)} · Vencimiento ${displayDate(invoice.due_at)} · Moneda ${escapeHtml(invoice.currency)}</p></section>
  <section class="section"><h2>Control del cálculo</h2><p>Importes derivados por el backend con Decimal.</p><div class="calc"><div class="value"><span>Neto</span><strong>${money(m.net)}</strong></div><div class="op">+</div><div class="value"><span>IGV</span><strong>${money(m.tax)}</strong></div><div class="op">=</div><div class="value"><span>Total derivado</span><strong>${money(m.derived_total)}</strong></div></div><div class="compare"><div class="value"><span>Total registrado</span><strong>${money(m.reported_total)}</strong></div><div class="value"><span>Diferencia absoluta observada</span><strong>${money(m.absolute_difference)}</strong></div></div></section>
  ${notes.length?`<section class="section"><h2>Ajustes post-emisión</h2><div class="flow"><div class="flow-card"><span>Factura original</span><strong>${escapeHtml(invoice.document)}</strong><span>${money(invoice.total)}</span></div><div class="arrow">→</div>${notes.map(note=>{const adjustment=(presentation.adjustments||[]).find(item=>item.credit_note?.document===note.document)||{};return `<div class="flow-card"><span>Nota de crédito</span><strong>${escapeHtml(note.document)}</strong><span>${money(note.total)} · ${percent(adjustment.ratio)}</span><span class="badge ${escapeHtml(adjustment.severity)}">${adjustment.material?`Ajuste material · ${escapeHtml(adjustment.severity_label)}`:"Ajuste documentado"}</span></div>`}).join('<div class="arrow">→</div>')}</div><p>La presencia o materialidad de una NC no confirma un error de facturación ni su motivo.</p></section>`:""}
  <section class="section"><h2>Hallazgos</h2>${findings(payload,presentation)}</section>${technical(payload)}`;
}

function renderGaps(payload,presentation) {
  const gaps=(payload.evidence||[]).filter(item=>item.type==="cycle_gap").map(item=>item.value);
  return `<div class="narrative">${escapeHtml(presentation.narrative)}</div><section class="section"><h2>Posibles quiebres documentales</h2><p>Ventana reproducible: documento cíclico en M y M+2, sin evidencia en M+1 para el mismo cliente y cuenta.</p>${gaps.length?gaps.map(gap=>{const plant=(payload.evidence||[]).find(item=>item.type==="linked_plant"&&item.id===`plant:${gap.customer}:${gap.account}`);const statuses=(plant?.value||[]).map(row=>plantStatusLabel(row.fixed_status||row.mobile_status)).filter(Boolean);return `<div class="flow"><div class="flow-card"><span>Periodo anterior · evidencia</span><strong>${escapeHtml(gap.before_period)}</strong><span>${escapeHtml(gap.before_document)}</span></div><div class="arrow">→</div><div class="flow-card"><span>Periodo sin evidencia documental</span><strong>${escapeHtml(gap.missing_period)}</strong><span>Requiere validación</span></div><div class="arrow">→</div><div class="flow-card"><span>Periodo posterior · evidencia</span><strong>${escapeHtml(gap.after_period)}</strong><span>${escapeHtml(gap.after_document)}</span></div></div><p>${escapeHtml(gap.customer)} · Cuenta ${escapeHtml(gap.account)} · Planta enlazada: ${plant?"Sí":"No"}${statuses.length?` · Estado ${escapeHtml([...new Set(statuses)].join(", "))}`:""}</p>`}).join(""):`<div class="empty">No se encontraron candidatos para los filtros y corte seleccionados.</div>`}</section><section class="section"><h2>Hallazgos</h2>${findings(payload,presentation)}</section>${technical(payload)}`;
}

function renderNotes(payload,presentation) {
  const adjustments=presentation.adjustments||[];
  return `<div class="narrative">${escapeHtml(presentation.narrative)}</div><section class="section"><h2>Ajustes post-emisión</h2><p>Ratio, materialidad y severidad provienen exclusivamente del backend.</p>${adjustments.length?`<div class="table-wrap"><table><thead><tr><th>Cliente</th><th>Cuenta</th><th>Factura</th><th>Monto factura</th><th>NC</th><th>Monto NC</th><th>Ratio</th><th>Fecha</th><th>Nivel</th></tr></thead><tbody>${adjustments.map(item=>`<tr><td>${escapeHtml(item.credit_note.customer)}</td><td>${escapeHtml(item.credit_note.account)}</td><td>${escapeHtml(item.invoice.document)}</td><td>${money(item.invoice.total)}</td><td>${escapeHtml(item.credit_note.document)}</td><td>${money(item.credit_note.total)}</td><td>${percent(item.ratio)}</td><td>${displayDate(item.credit_note.issued_at)}</td><td><span class="badge ${escapeHtml(item.severity)}">${escapeHtml(item.severity_label)}</span></td></tr>`).join("")}</tbody></table></div>`:`<div class="empty">No se encontraron notas de crédito en el alcance.</div>`}</section><section class="section"><h2>Hallazgos</h2>${findings(payload,presentation)}</section>${technical(payload)}`;
}

function renderTool(envelope) {
  const payload=envelope.agent_response, presentation=envelope.presentation;
  const renderers={customer_billing_check:renderCustomer,invoice_quality_check:renderInvoice,billing_cycle_gaps:renderGaps,credit_note_review:renderNotes};
  const renderer=renderers[payload.operation];
  if (!renderer) throw new Error(`Operación no soportada por esta vista: ${payload.operation}`);
  $("#content").innerHTML=renderer(payload,presentation);
  $("#feedback").className="notice";
  $("#feedback").textContent=`Análisis completado · ${payload.operation} · ${presentation.status_labels?.billing_assurance || "Resultado disponible"}`;
}

function readControls() {
  state.asOf=$("#asof")?.value||state.asOf;
  ["customer","account","invoice","threshold","question"].forEach(key=>{const element=$("#"+key);if(element)state[key]=element.value.trim()});
}

async function loadView() {
  readControls();
  if (state.datasetStatus?.status !== "READY") {
    showDatasetNotConfigured();
    return;
  }
  $("#feedback").className="notice"; $("#feedback").textContent="Analizando evidencia disponible…";
  try {
    if (state.view==="agent") {
      const result=await requestJson("/api/conversation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:state.question,dataset_id:state.datasetId,as_of_date:state.asOf,context:state.context})});
      state.context=result.context||{};
      $("#feedback").textContent=`${result.route === "llm" ? "Interpretación asistida" : "Respuesta determinística"} · ${result.tool || result.status}`;
      $("#content").innerHTML=`<div id="agent-answer" class="narrative"></div>${result.agent_response?`<section class="section"><h2>Hallazgos respaldados</h2>${findings(result.agent_response,result.presentation)}</section>`:""}<details><summary>Ver trazabilidad de enrutamiento</summary><pre>${escapeHtml(JSON.stringify(result,null,2))}</pre></details>`;
      const answerTarget = $("#agent-answer");
      if (window.SoniaMarkdown?.render) window.SoniaMarkdown.render(answerTarget, result.answer);
      else answerTarget.textContent = String(result.answer || "");
      return;
    }
    if (state.view==="summary") {
      renderWorkQueue(await requestJson(apiUrl("/api/work-queue", {as_of_date:state.asOf})));
      $("#feedback").className="notice";
      $("#feedback").textContent="Bandeja actualizada · casos agrupados y priorizados por reglas verificables";
      return;
    }
    let path="/api/health", params={as_of_date:state.asOf};
    if(state.view==="customer"){path="/api/customer";params={...params,customer_id:state.customer,account_id:state.account}}
    if(state.view==="invoice"){path="/api/invoice";params={...params,invoice_id:state.invoice}}
    if(state.view==="gaps"){path="/api/gaps";params={...params,customer_id:state.customer,account_id:state.account}}
    if(state.view==="notes"){path="/api/credit-notes";params={...params,invoice_id:state.invoice,materiality_threshold:state.threshold}}
    renderTool(await requestJson(apiUrl(path,params)));
  } catch(error) {
    $("#feedback").className="notice error"; $("#feedback").textContent=error.message;
    $("#content").innerHTML=`<div class="empty">No fue posible completar el análisis. Corrige la entrada o valida la fuente de datos.</div>`;
  }
}

document.querySelectorAll(".nav button").forEach(button=>button.onclick=()=>selectView(button.dataset.view));

(async function initialize(){try{const ready=await refreshDatasetStatus("default");controls();ready?await loadView():showDatasetNotConfigured()}catch(error){controls();$("#feedback").className="notice error";$("#feedback").textContent=error.message;$("#content").innerHTML='<div class="empty">No fue posible consultar el estado de la fuente de datos.</div>'}})();
