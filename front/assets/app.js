const STATE_ORDER = [
  "BILLING_RUNNING",
  "BILLING_JUDGING",
  "COLLECTIONS_RUNNING",
  "COLLECTIONS_JUDGING",
  "BI_RUNNING",
  "BI_JUDGING",
  "COMPLETED",
];

const STATE_COPY = {
  VALIDATING: {
    label: "Validando PxQ",
    title: "Validar insumos de facturación",
    description: "Facturación verificará cantidad, tarifa, periodo, moneda y total con evidencia.",
    action: "VALIDATE_PXQ",
    button: "Ejecutar validación",
    human: false,
  },
  NEEDS_APPROVAL: {
    label: "Requiere aprobación",
    title: "Autorizar emisión simulada",
    description: "Las reglas pasaron. Una persona debe confirmar antes de emitir el documento.",
    action: "APPROVE_INVOICE",
    button: "Aprobar emisión",
    human: true,
  },
  ISSUED: {
    label: "Factura emitida",
    title: "Analizar comunicación de pago",
    description: "Cobranzas clasificará el mensaje ficticio y buscará una referencia verificable.",
    action: "ANALYZE_PAYMENT",
    button: "Procesar mensaje",
    human: false,
  },
  PAYMENT_DETECTED: {
    label: "Pago detectado",
    title: "Preparar conciliación",
    description: "Recaudo comparará factura y depósito antes de proponer la aplicación.",
    action: "PREPARE_RECONCILIATION",
    button: "Validar coincidencias",
    human: false,
  },
  RECONCILING: {
    label: "Requiere confirmación",
    title: "Confirmar aplicación del pago",
    description: "Los cinco criterios coinciden. La decisión final permanece bajo control humano.",
    action: "CONFIRM_PAYMENT",
    button: "Confirmar aplicación",
    human: true,
  },
  ANALYZING: {
    label: "Analizando indicadores",
    title: "Generar lectura ejecutiva",
    description: "BI consolidará ingresos, cartera y conciliación en indicadores explicables.",
    action: "GENERATE_INSIGHTS",
    button: "Generar indicadores",
    human: false,
  },
  CLOSED: {
    label: "Caso cerrado",
    title: "Journey completado",
    description: "Factura y pago quedaron conciliados con evidencia y auditoría E2E.",
    action: null,
    button: "Completado",
    human: false,
  },
};

const AGENT_CONFIG = window.SONIA_AGENT_UI;

const EVENT_COLORS = {
  blue: "#019be1",
  green: "#0b9b75",
  violet: "#8b73e8",
  amber: "#e4a13e",
  navy: "#75d6ff",
  gray: "#8096a1",
};

const appState = {
  scenario: null,
  currentState: "VALIDATING",
  progress: 0,
  selectedAgent: "billing",
  timeline: [],
  busy: false,
  datasetRevision: null,
  rulesetRevision: null,
  runId: null,
  packageRevision: null,
};

const byId = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function statusForAgent(agentId) {
  const index = STATE_ORDER.indexOf(appState.currentState);
  if (agentId === "billing") {
    if (index <= 0) return "active";
    if (index === 1) return "review";
    return "completed";
  }
  if (agentId === "collections") {
    if (index < 2) return "pending";
    if (index === 2) return "active";
    return "completed";
  }
  if (index < 5) return "pending";
  if (index === 5) return "active";
  return "completed";
}

function statusLabel(status) {
  return {
    pending: "En espera",
    active: "Trabajando",
    review: "Revisión humana",
    completed: "Completado",
  }[status];
}

function renderAgents() {
  const grid = byId("agent-grid");
  grid.innerHTML = appState.scenario.agents
    .map((agent) => {
      const theme = AGENT_CONFIG[agent.agent_id].theme;
      const status = statusForAgent(agent.agent_id);
      const selected = appState.selectedAgent === agent.agent_id;
      return `
        <button
          class="agent-card ${selected ? "is-selected" : ""}"
          type="button"
          data-agent-id="${escapeHtml(agent.agent_id)}"
          aria-pressed="${selected}"
          style="--agent-color:${theme.color};--agent-pale:${theme.pale}"
        >
          <span class="agent-topline">
            <span class="agent-number">${theme.number}</span>
            <span class="agent-state">${statusLabel(status)}</span>
          </span>
          <h3>${escapeHtml(agent.name)}</h3>
          <span class="agent-specialty">${escapeHtml(agent.specialty)}</span>
          <p>${escapeHtml(agent.summary)}</p>
          <span class="agent-stats">
            <span><strong>${agent.confidence}%</strong>confianza</span>
            <span><strong>${agent.evidence_count}</strong>evidencias</span>
          </span>
        </button>`;
    })
    .join("");

  grid.querySelectorAll("[data-agent-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const agentId = button.dataset.agentId;
      const agentHref = AGENT_CONFIG[agentId].href;
      if (agentHref) {
        window.location.assign(agentHref);
        return;
      }
      appState.selectedAgent = agentId;
      renderAgents();
      renderInspector();
    });
  });
}

function renderInspector() {
  const agent = appState.scenario.agents.find(
    (candidate) => candidate.agent_id === appState.selectedAgent,
  );
  const config = AGENT_CONFIG[agent.agent_id];
  const theme = config.theme;
  const status = statusForAgent(agent.agent_id);
  const inspector = document.querySelector(".agent-inspector");
  inspector.style.borderColor = theme.color;
  inspector.style.background = theme.pale;
  byId("inspector-kicker").textContent = statusLabel(status);
  byId("inspector-name").textContent = `Agente de ${agent.name}`;
  byId("inspector-confidence").textContent = `${agent.confidence}% confianza`;
  byId("inspector-summary").textContent = agent.summary;
  byId("inspector-findings").innerHTML = config.findings
    .map((finding) => `<li>${escapeHtml(finding)}</li>`)
    .join("");
}

function renderJourney() {
  const currentIndex = STATE_ORDER.indexOf(appState.currentState);
  document.querySelectorAll("[data-step-state]").forEach((step) => {
    const stepIndex = STATE_ORDER.indexOf(step.dataset.stepState);
    step.classList.toggle("is-current", stepIndex === currentIndex);
    step.classList.toggle("is-complete", stepIndex < currentIndex);
  });
  byId("journey-progress").style.width = `${appState.progress}%`;
  byId("hero-progress").textContent = `${appState.progress}%`;
}

function renderTimeline() {
  byId("timeline").innerHTML = appState.timeline
    .slice(0, 5)
    .map(
      (event) => `
        <li style="--event-color:${EVENT_COLORS[event.tone] || EVENT_COLORS.gray}">
          <span class="timeline-meta"><span>${escapeHtml(event.actor)}</span><time>${escapeHtml(event.time)}</time></span>
          <strong>${escapeHtml(event.title)}</strong>
          <p>${escapeHtml(event.detail)}</p>
        </li>`,
    )
    .join("");
}

function renderAction() {
  const copy = STATE_COPY[appState.currentState];
  const button = byId("primary-action");
  byId("next-title").textContent = copy.title;
  byId("next-description").textContent = copy.description;
  byId("action-label").textContent = appState.busy ? "Procesando…" : copy.button;
  byId("human-gate").hidden = !copy.human;
  button.hidden = appState.currentState === "CLOSED";
  button.disabled = appState.busy || !copy.action;
  byId("reset-action").hidden = appState.currentState !== "CLOSED";
}

function renderState() {
  const copy = STATE_COPY[appState.currentState];
  const status = byId("case-status");
  byId("hero-state").textContent = copy.label;
  status.textContent = copy.label;
  status.className = "status-chip";
  if (copy.human) status.classList.add("human");
  if (appState.currentState === "CLOSED") status.classList.add("closed");
  renderJourney();
  renderAgents();
  renderInspector();
  renderAction();
  renderTimeline();
}

function renderScenario() {
  const scenario = appState.scenario;
  byId("hero-case-id").textContent = scenario.case_id;
  byId("case-id").textContent = scenario.case_id;
  byId("customer-name").textContent = scenario.customer_name;
  byId("service-name").textContent = scenario.service_name;
  byId("invoice-reference").textContent = scenario.invoice_reference;
  byId("invoice-amount").textContent = scenario.invoice_amount;
  byId("currency").textContent = scenario.currency;
  byId("metric-time").textContent = scenario.metrics[0].value;
  byId("metric-evidence").textContent = scenario.metrics[1].value;
  byId("metric-actions").textContent = scenario.metrics[2].value;
  renderState();
}

function showToast(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.add("is-visible");
  window.setTimeout(() => toast.classList.remove("is-visible"), 2800);
}

function renderDatasetStatus(payload) {
  const ready = payload.dataset_configured === true;
  const status = byId("supervisor-dataset-status");
  status.textContent = ready ? "Publicado para 3 agentes" : "Pendiente de publicación";
  status.className = `pill ${ready ? "dataset-ready" : "neutral"}`;
  byId("dataset-hub-summary").textContent = ready
    ? `${payload.dataset_file_count} fuentes · ${payload.dataset_bytes} bytes · administrado por Supervisor.`
    : "Publica las seis fuentes oficiales una sola vez para Facturación, Cobranzas y BI.";
  const labels = { billing: "Facturación", collections: "Cobranzas", bi: "BI" };
  byId("dataset-agent-status").innerHTML = Object.entries(payload.agents || {})
    .map(([agent, state]) => `
      <span class="dataset-agent-chip ${state.dataset_configured ? "ready" : "pending"}">
        <strong>${labels[agent] || agent}</strong>
        ${state.dataset_configured ? "Disponible" : "Sin publicar"}
      </span>`)
    .join("");
}

async function loadDatasetStatus() {
  try {
    const response = await fetch("/api/supervisor/dataset");
    if (!response.ok) throw new Error(`Dataset status failed with ${response.status}`);
    renderDatasetStatus(await response.json());
  } catch (error) {
    console.error(error);
    byId("supervisor-dataset-status").textContent = "Estado no disponible";
  }
}

async function publishDataset() {
  const files = [...byId("supervisor-dataset-files").files];
  const result = byId("dataset-publish-result");
  const button = byId("publish-dataset");
  const validSelection = files.length === 1 || files.length === 6;
  if (!validSelection) {
    result.textContent = "Selecciona las seis fuentes CSV o un único ZIP compatible.";
    result.className = "dataset-publish-result error";
    return;
  }
  const form = new FormData();
  files.forEach((file) => form.append("files", file, file.name));
  button.disabled = true;
  button.textContent = "Validando los tres agentes…";
  result.textContent = "La publicación será atómica: ningún agente cambia hasta validar todo.";
  result.className = "dataset-publish-result";
  try {
    const response = await fetch("/api/supervisor/datasets", {
      method: "POST",
      headers: { "Idempotency-Key": operationKey("dataset") },
      body: form,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "El dataset no es compatible.");
    appState.datasetRevision = payload.dataset_revision;
    result.textContent = `Dataset ${payload.dataset_revision} publicado para los tres especialistas.`;
    result.className = "dataset-publish-result success";
    await loadDatasetStatus();
    await loadQuestions();
    showToast("Fuente compartida publicada por Supervisor.");
  } catch (error) {
    result.textContent = error.message || "No se pudo publicar el dataset.";
    result.className = "dataset-publish-result error";
  } finally {
    button.disabled = false;
    button.textContent = "Validar y publicar";
  }
}

const operationKey = (scope) => `${scope}-${crypto.randomUUID()}`;

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || `Error HTTP ${response.status}`);
  return payload;
}

async function loadQuestions() {
  const questions = await api(
    `/api/supervisor/datasets/${appState.datasetRevision}/questions`,
  );
  const container = byId("rule-questions");
  container.replaceChildren();
  questions.forEach((question) => {
    const label = document.createElement("label");
    label.textContent = `${question.target} · ${question.question_id}`;
    const input = document.createElement("input");
    input.name = question.question_id;
    input.type = ["date", "number"].includes(question.answer_type)
      ? question.answer_type
      : "text";
    input.required = question.mandatory !== false;
    label.append(input);
    container.append(label);
  });
  byId("rule-card").hidden = false;
  byId("rules-form").hidden = false;
}

async function startRun(event) {
  event.preventDefault();
  setBusy(true);
  try {
    const answers = Object.fromEntries(new FormData(event.currentTarget));
    const ruleset = await api("/api/supervisor/rulesets", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ dataset_revision: appState.datasetRevision, answers }),
    });
    appState.rulesetRevision = ruleset.revision_id;
    const run = await api("/api/supervisor/runs", {
      method: "POST",
      headers: { "content-type": "application/json", "Idempotency-Key": operationKey("run") },
      body: JSON.stringify({
        dataset_revision: appState.datasetRevision,
        ruleset_revision: appState.rulesetRevision,
      }),
    });
    appState.runId = run.run_id;
    byId("hero-case-id").textContent = appState.runId;
    await api(`/api/supervisor/runs/${appState.runId}/start`, {
      method: "POST",
      headers: { "Idempotency-Key": operationKey("start") },
    });
    await pollRun();
  } catch (error) {
    showToast(error.message);
    setBusy(false);
  }
}

function renderRecords(id, records) {
  const target = byId(id);
  target.textContent = records
    .map((record) =>
      typeof record === "string"
        ? record
        : `${record.phase} · ${record.kind}\n${JSON.stringify(record.content, null, 2)}`,
    )
    .join("\n");
}

async function pollRun() {
  const base = `/api/supervisor/runs/${appState.runId}`;
  const run = await api(base);
  byId("run-progress").textContent = `${run.state} · ${run.run_id}`;
  byId("hero-state").textContent = run.state;
  const index = STATE_ORDER.indexOf(run.state);
  if (index >= 0) {
    appState.currentState = run.state;
    appState.progress = Math.round((index / (STATE_ORDER.length - 1)) * 100);
    renderJourney();
  }
  if (!["COMPLETED", "MANUAL_REVIEW"].includes(run.state)) {
    window.setTimeout(pollRun, 1000);
    return;
  }
  const [history, evidence, packageData] = await Promise.all([
    api(`${base}/history`),
    api(`${base}/evidence`),
    api(`${base}/package`),
  ]);
  renderRecords("judge-history", history.history);
  renderRecords("evidence-output", evidence.evidence);
  appState.packageRevision = packageData.package_revision;
  byId("package-output").textContent = JSON.stringify(packageData.envelope, null, 2);
  byId("review-form").hidden = false;
  setBusy(false);
  try {
    lockReview(await api(`${base}/review`));
  } catch (error) {
    if (!error.message.includes("not found")) console.debug(error);
  }
}

async function submitReview(event) {
  event.preventDefault();
  const values = Object.fromEntries(new FormData(event.currentTarget));
  for (const field of ["reason", "annotation"])
    if (!values[field]?.trim()) delete values[field];
  try {
    const decision = await api(`/api/supervisor/runs/${appState.runId}/review`, {
      method: "POST",
      headers: { "content-type": "application/json", "Idempotency-Key": operationKey("review") },
      body: JSON.stringify({ package_revision: appState.packageRevision, ...values }),
    });
    lockReview(decision);
  } catch (error) {
    showToast(error.message);
  }
}

function lockReview(decision) {
  byId("review-status").textContent = `Decisión registrada: ${decision.outcome}`;
  byId("review-form").querySelector("fieldset").disabled = true;
}

function syncReviewReason() {
  byId("review-reason").required = byId("review-outcome").value === "reject";
}

function setBusy(value) {
  byId("run-progress").setAttribute("aria-busy", String(value));
  byId("start-run").disabled = value;
}

byId("supervisor-dataset-files").addEventListener("change", (event) => {
  const count = event.target.files.length;
  byId("dataset-file-label").textContent = count
    ? `${count} archivo${count === 1 ? "" : "s"} seleccionado${count === 1 ? "" : "s"}`
    : "Seleccionar seis CSV o un ZIP";
});
byId("publish-dataset").addEventListener("click", publishDataset);
byId("rules-form").addEventListener("submit", startRun);
byId("review-form").addEventListener("submit", submitReview);
byId("review-outcome").addEventListener("change", syncReviewReason);
syncReviewReason();
loadDatasetStatus();
