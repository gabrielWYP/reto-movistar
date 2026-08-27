export const API_BASE = "/api/collections";
export const API_LIST_LIMIT = 500;
export const FEATURED_CASE_LIMIT = 3;

export const PROCESS_META = {
  collection: {
    label: "Cobranza",
    description: "¿Qué falta recuperar y qué debemos gestionar primero?",
    views: ["portfolio", "priorities", "customer", "invoice"],
  },
  revenue: {
    label: "Recaudación",
    description: "¿Qué pagos llegaron, cómo se aplicaron y cuáles requieren revisión?",
    views: ["exceptions"],
  },
};

export const VIEW_META = {
  portfolio: { label: "Cartera", process: "collection" },
  priorities: { label: "Prioridades", process: "collection" },
  customer: { label: "Cliente", process: "collection" },
  invoice: { label: "Factura", process: "collection" },
  exceptions: { label: "Conciliación documental", process: "revenue" },
};

export const SEVERITY_META = {
  HIGH: { label: "Alta", tone: "danger", icon: "!" },
  CRITICA: { label: "Crítica", tone: "danger", icon: "!" },
  MEDIUM: { label: "Media", tone: "warning", icon: "△" },
  VENCIDA: { label: "Vencida", tone: "warning", icon: "△" },
  LOW: { label: "Baja", tone: "success", icon: "✓" },
  INFO: { label: "Informativa", tone: "info", icon: "i" },
  PAGADA: { label: "Pagada", tone: "success", icon: "✓" },
  CONCILIADA: { label: "Validada documentalmente", tone: "success", icon: "✓" },
  PAGO_PARCIAL: { label: "Pago parcial", tone: "warning", icon: "△" },
  REQUIERE_REVISION: { label: "Requiere validación", tone: "warning", icon: "△" },
  PENDIENTE: { label: "Pendiente de pago", tone: "neutral", icon: "•" },
  PENDIENTE_DE_PAGO: { label: "Sin pago aplicado", tone: "neutral", icon: "•" },
  PARCIALMENTE_CONCILIADA: { label: "Aplicación parcial", tone: "warning", icon: "△" },
  SALDO_A_FAVOR: { label: "Saldo a favor por validar", tone: "warning", icon: "△" },
  NO_VENCIDA: { label: "Pendiente, aún no vencida", tone: "info", icon: "i" },
  NO_APLICA: { label: "Sin saldo pendiente", tone: "neutral", icon: "•" },
  AL_DIA: { label: "Al día al corte", tone: "success", icon: "✓" },
};

export const OPERATIONAL_STATES = {
  PENDIENTE_VALIDACION: { label: "Pendiente de validación", tone: "warning" },
  EN_REVISION: { label: "En revisión", tone: "info" },
  REVISADO: { label: "Revisado", tone: "success" },
  ESCALAR: { label: "Escalar", tone: "danger" },
};

export const INVOICE_STATES = {
  PENDIENTE_GESTION: { label: "Pendiente", tone: "warning" },
  REVISADO: { label: "Revisado", tone: "success" },
};

export const SORT_OPTIONS = [
  { value: "priority_score", label: "Índice de prioridad" },
  { value: "overdue_balance", label: "Saldo vencido" },
  { value: "max_days_past_due", label: "Mayor atraso" },
  { value: "overdue_share", label: "% vencido" },
];

export const BUCKET_LABELS = {
  NO_VENCIDA: "Aún no vencida",
  "1_30": "De 1 a 30 días vencida",
  "31_60": "De 31 a 60 días vencida",
  "61_90": "De 61 a 90 días vencida",
  "90_PLUS": "Más de 90 días vencida",
  SIN_FECHA_VENCIMIENTO: "Sin fecha de vencimiento",
};

export const FINDING_LABELS = {
  UNMATCHED_PAYMENT_CUTOFF: "Pago sin factura dentro del corte analizado",
  OVERDUE_EXPOSURE: "Saldo vencido que requiere gestión",
  OPEN_BALANCE: "Factura con saldo pendiente",
  OVERAPPLICATION: "Aplicación por revisar",
  TEMPORAL_ANOMALY: "Fecha de pago por validar",
  PAYMENT_OUTSIDE_INVOICE_CUTOFF: "Pago sin factura dentro del corte",
  PAYMENT_BEFORE_ISSUANCE: "Pago anterior a la emisión",
  PAYMENT_LINK_MISMATCH: "Relación cliente, cuenta y factura por validar",
  CREDIT_NOTE_OUTSIDE_INVOICE_CUTOFF: "Nota de crédito sin factura dentro del corte",
  DOCUMENT_SETTLED: "Documento sin incidencias detectadas",
  SCORING_RULE: "Criterios de priorización aplicados",
};

export const ACTION_LABELS = {
  review_collection_priorities: "Ver clientes prioritarios",
  review_unmatched_payments: "Revisar pagos fuera del corte",
  prioritize_internal_management: "Priorizar gestión interna",
  monitor: "Mantener seguimiento",
  review_overapplication: "Abrir conciliación documental",
  start_collection: "Priorizar gestión",
  monitor_due_date: "Dar seguimiento al vencimiento",
  close_case: "Marcar revisado",
  assign_collection_queue: "Marcar para gestión",
  review_exceptions: "Revisar casos de aplicación",
};
