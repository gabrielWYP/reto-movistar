const STATE_ORDER = [
  "VALIDATING",
  "NEEDS_APPROVAL",
  "ISSUED",
  "PAYMENT_DETECTED",
  "RECONCILING",
  "ANALYZING",
  "CLOSED",
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

async function performTransition() {
  const copy = STATE_COPY[appState.currentState];
  if (!copy.action || appState.busy) return;
  appState.busy = true;
  renderAction();

  try {
    const response = await fetch("/api/demo/transition", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ current_state: appState.currentState, action: copy.action }),
    });
    if (!response.ok) throw new Error(`Transition failed with status ${response.status}`);
    const result = await response.json();
    appState.currentState = result.current_state;
    appState.progress = result.progress;
    appState.timeline.unshift(result.event);
    const activeAgent = ["ANALYZING", "CLOSED"].includes(result.current_state)
      ? "bi"
      : ["ISSUED", "PAYMENT_DETECTED", "RECONCILING"].includes(result.current_state)
        ? "collections"
        : "billing";
    appState.selectedAgent = activeAgent;
    showToast(result.event.title);
  } catch (error) {
    console.error(error);
    showToast("No se pudo completar la transición. Intenta nuevamente.");
  } finally {
    appState.busy = false;
    renderState();
  }
}

function resetDemo() {
  appState.currentState = appState.scenario.current_state;
  appState.progress = appState.scenario.progress;
  appState.timeline = [...appState.scenario.timeline];
  appState.selectedAgent = "billing";
  renderState();
  showToast("Demo reiniciada con datos ficticios.");
}

async function initialize() {
  try {
    const response = await fetch("/api/demo/scenario");
    if (!response.ok) throw new Error(`Scenario failed with status ${response.status}`);
    appState.scenario = await response.json();
    appState.currentState = appState.scenario.current_state;
    appState.progress = appState.scenario.progress;
    appState.timeline = [...appState.scenario.timeline];
    renderScenario();
  } catch (error) {
    console.error(error);
    byId("next-title").textContent = "No pudimos cargar la demo";
    byId("next-description").textContent = "Verifica la conexión y vuelve a cargar la página.";
    showToast("Error al cargar el escenario.");
  }
}

byId("primary-action").addEventListener("click", performTransition);
byId("reset-action").addEventListener("click", resetDemo);
initialize();
