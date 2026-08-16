const QUESTIONS = [
  "¿Cómo está el ciclo de ingresos al 31 de julio?",
  "¿Dónde está concentrado el saldo vencido?",
  "¿Qué oportunidades de recupero tenemos?",
  "¿Qué debería priorizar la gerencia?",
  "¿Qué limitaciones tiene la información?",
];

const TOOL_LABELS = {
  executive_snapshot: "Resumen del ciclo de ingresos",
  risk_concentration: "Concentración de riesgo",
  recovery_intelligence: "Oportunidades de recupero",
  management_insights: "Prioridades para la gerencia",
  data_quality_report: "Calidad y alcance de la información",
};

const byId = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.setTimeout(() => toast.classList.remove("visible"), 3200);
}

function renderKpis(kpis = []) {
  byId("kpis").innerHTML = kpis
    .slice(0, 5)
    .map((item) => `<article class="kpi-card">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.display_value)}</strong>
      <small>${escapeHtml(item.help)}</small>
    </article>`)
    .join("");
}

function renderChart(component) {
  const rows = component.data || [];
  const maximum = Math.max(...rows.map((row) => Number(row.amount) || 0), 1);
  return `<article class="visual-card">
    <header><h3>${escapeHtml(component.title)}</h3><p>${escapeHtml(component.description)}</p></header>
    <div class="bars">${rows.map((row) => {
      const visualWidth = Math.max(3, ((Number(row.amount) || 0) / maximum) * 100);
      return `<div class="bar-row">
        <div class="bar-label"><strong>${escapeHtml(row.label)}</strong><span>${escapeHtml(row.display_amount)}${row.display_share ? ` · ${escapeHtml(row.display_share)}` : ""}</span></div>
        <div class="bar-track"><span style="width:${visualWidth.toFixed(2)}%"></span></div>
      </div>`;
    }).join("")}</div>
  </article>`;
}

function renderTable(component) {
  return `<article class="visual-card table-card">
    <header><h3>${escapeHtml(component.title)}</h3><p>${escapeHtml(component.description)}</p></header>
    <div class="table-wrap"><table><thead><tr>${component.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
    <tbody>${component.rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
  </article>`;
}

function renderComponents(components = []) {
  byId("visual-components").innerHTML = components
    .map((component) => {
      if (["bar_chart", "pareto_chart"].includes(component.type)) return renderChart(component);
      if (component.type === "table") return renderTable(component);
      return "";
    })
    .join("");
}

function renderStories(sectionId, targetId, items, tone) {
  const section = byId(sectionId);
  section.hidden = !items?.length;
  byId(targetId).innerHTML = (items || []).map((item) => `<article class="story-card ${tone}">
    <h3>${escapeHtml(item.title)}</h3>
    <p>${escapeHtml(item.detail)}</p>
    ${item.impact ? `<small>${escapeHtml(item.impact)}</small>` : ""}
  </article>`).join("");
}

function renderResult(payload) {
  const view = payload.presentation || {};
  const analysis = view.analysis || {};
  byId("analysis-title").textContent = analysis.title || TOOL_LABELS[payload.tool_used] || "Análisis BI";
  byId("analysis-date").textContent = `Corte: ${analysis.as_of_date || payload.agent_response?.as_of_date || "—"}`;
  byId("answer").textContent = payload.answer || "Resultado disponible en la evidencia.";
  const aiGenerated = payload.mode === "llm";
  byId("ai-badge").hidden = !aiGenerated;
  byId("execution-mode").textContent = aiGenerated
    ? `Respuesta generada por ${payload.llm?.provider || "IA"} · ${payload.llm?.model || "modelo configurado"} · cálculos verificables`
    : payload.mode === "deterministic_fallback"
      ? "Respuesta verificable sin IA · el proveedor no estuvo disponible"
      : "Análisis basado en reglas verificables";
  renderKpis(view.kpis);
  renderComponents(view.components);
  renderStories("findings-section", "findings", view.findings, "finding");
  renderStories("actions-section", "actions", view.recommended_actions, "action");
  renderStories("alerts-section", "alerts", view.alerts, "alert");
  byId("trace-summary").innerHTML = `<span><strong>Tool</strong>${escapeHtml(payload.tool_used)}</span>
    <span><strong>Parámetros</strong>${escapeHtml(JSON.stringify(payload.tool_arguments || {}))}</span>
    <span><strong>Modo</strong>${escapeHtml(payload.mode)}</span>`;
  byId("raw-json").textContent = JSON.stringify(payload, null, 2);
  byId("empty-state").hidden = true;
  byId("result").hidden = false;
}

async function queryAgent(question) {
  const button = byId("submit-query");
  const form = byId("query-form");
  button.disabled = true;
  form.setAttribute("aria-busy", "true");
  button.firstChild.textContent = "Consultando IA… ";
  try {
    const response = await fetch("/api/bi/query", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ question, as_of_date: byId("as-of-date").value }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Error HTTP ${response.status}`);
    renderResult(payload);
  } catch (error) {
    showToast(error.message || "No se pudo completar la consulta.");
  } finally {
    button.disabled = false;
    form.removeAttribute("aria-busy");
    button.firstChild.textContent = "Analizar ";
  }
}

async function uploadDataset(files) {
  if (!files.length) {
    showToast("Selecciona al menos un CSV o ZIP.");
    return;
  }
  const button = byId("upload-dataset");
  const form = new FormData();
  Array.from(files).forEach((file) => form.append("files", file));
  button.disabled = true;
  button.textContent = "Cargando…";
  try {
    const response = await fetch("/api/bi/dataset", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `Error HTTP ${response.status}`);
    showToast(payload.dataset_configured ? "Dataset listo en memoria." : "Carga parcial guardada.");
    await loadStatus();
  } catch (error) {
    showToast(error.message || "No se pudo cargar el dataset.");
  } finally {
    button.disabled = false;
    button.textContent = "Cargar dataset";
  }
}

async function loadStatus() {
  try {
    const response = await fetch("/api/bi/status");
    const status = await response.json();
    const label = status.dataset_configured ? "Dataset listo" : "Dataset pendiente";
    const aiStatus = status.llm_available
      ? `${status.llm.provider} · ${status.llm.model}`
      : "IA no configurada · fallback verificable";
    byId("system-status").textContent = `${label} · ${aiStatus}`;
    byId("system-status").classList.toggle("ready", status.dataset_configured);
    byId("dataset-summary").textContent = status.dataset_configured
      ? `${status.dataset_file_count} archivos · ${status.dataset_bytes} bytes en memoria · se perderán al reiniciar.`
      : `${status.dataset_file_count} archivos cargados · faltan ${status.missing_files.length}.`;
  } catch {
    byId("system-status").textContent = "Backend no disponible";
  }
}

byId("suggestions").innerHTML = QUESTIONS.map((question) =>
  `<button type="button" data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`,
).join("");

byId("suggestions").addEventListener("click", (event) => {
  const button = event.target.closest("[data-question]");
  if (!button) return;
  byId("question").value = button.dataset.question;
  queryAgent(button.dataset.question);
});

byId("query-form").addEventListener("submit", (event) => {
  event.preventDefault();
  queryAgent(byId("question").value.trim());
});

byId("upload-dataset").addEventListener("click", () => {
  uploadDataset(byId("dataset-files").files);
});

loadStatus();
