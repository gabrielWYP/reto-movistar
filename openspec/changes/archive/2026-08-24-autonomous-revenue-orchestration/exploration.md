## Exploration: Autonomous Revenue Orchestration

### Current State

Supervisor already owns the single manual publication boundary. `SupervisorDatasetCoordinator`
normalizes the six CSV files, validates candidate services for Billing, Collections, and BI, and
publishes them atomically in process memory. The publication has no dataset revision/hash, durable
record, or workflow trigger, and it is lost when the backend pod restarts.

The apparent end-to-end journey is not connected to that dataset. `demo_service.py` returns a fixed
fictional scenario and applies stateless transitions selected by the browser. The client supplies the
current state and manually advances each step; there is no persisted run, task ownership, actual
specialist execution, retry, Judge, or reconstructable audit log.

Each specialist currently behaves as an independent query/tool facade:

- Billing exposes five deterministic evidence-first checks with optional OpenCode routing.
- Collections exposes five deterministic portfolio/reconciliation tools and an OpenCode tool loop.
- BI exposes five deterministic analytical tools with optional OpenCode selection and narration.

This is a useful execution substrate: calculations and validations remain in typed Python, tool
catalogues are closed, and responses already contain status, findings, alerts, evidence, data-quality
metadata, and recommended actions. However, their output contracts are heterogeneous and no shared
runtime passes an approved Billing artifact to Collections or approved upstream artifacts to BI.
`bi_agent.integration` currently records Collections provenance as `reference_only`.

### Affected Areas

- `back/src/sonia/application/dataset_supervisor.py` — assign an immutable dataset revision and make
  successful publication open the business-rule intake boundary without directly running on upload.
- `back/src/sonia/application/demo_service.py` — replace the fictional transition driver with a real
  workflow application service, or retire it behind an explicitly separate demo contract.
- `back/src/sonia/domain/demo.py` — replace presentation-only states with typed run, phase, gate,
  evidence, analyst-review, retry, and terminal-state contracts.
- `back/src/sonia/entrypoints/api.py` — expose run creation, rule submission, start/status, phase
  evidence, and analyst-review endpoints while preserving one shared API process.
- `back/src/sonia/application/agent_registry.py` — evolve static metadata into typed specialist
  adapters that can execute approved plans without invoking specialist HTTP endpoints internally.
- `Agente_Facturacion/BACK/src/billing_agent/{agent,runtime,service}.py` — provide a deterministic
  orchestration adapter and normalized validation result while preserving the closed tool catalogue.
- `Agente Cobranzas/BACK/src/collections_agent/{agent,application,service}.py` — provide the same
  adapter and accept approved upstream evidence references, not unvalidated model prose.
- `Agente BI/BACK/src/bi_agent/{agent,application,integration,service}.py` — replace reference-only
  provenance with an approved upstream-artifact contract for the final synthesis.
- `back/src/sonia/persistence/` — add a store interface and append-only workflow/audit implementation;
  no durable implementation exists today.
- `front/index.html` and `front/assets/app.js` — change the fictional click-through journey into:
  upload, business-rule intake, autonomous run progress, Judge decisions, evidence inspection, and
  analyst verification.
- `back/tests/unit/` and `back/tests/integration/` — cover state ownership, idempotency, retries,
  Judge gates, partial failure, restart recovery, evidence lineage, and forbidden transition skips.

### Approaches

1. **Central typed orchestrator with model-assisted planning and judging** — create one workflow run
   per dataset revision and rule set. A central state machine executes Billing, Judge, Collections,
   Judge, BI, and final Judge sequentially through in-process adapters. The LLM may map business
   questions to closed tools and assess qualitative completeness, while deterministic schemas,
   evidence checks, thresholds, and transition rules retain authority.
   - Pros: Reuses all existing deterministic services; preserves the shared two-container topology;
     provides one state owner, auditable gates, bounded retries, and testable idempotency; keeps model
     output away from direct state mutation and calculations.
   - Cons: Requires a normalized specialist-result envelope, durable run/audit storage, explicit
     upstream artifact contracts, and careful cancellation/retry semantics.
   - Effort: High

2. **Event-driven specialists with a broker and independent workers** — publish phase commands and
   results through a queue, with the Judge and each specialist consuming events independently.
   - Pros: Strong isolation, horizontal scaling, natural asynchronous retries, and long-running job
     support.
   - Cons: Introduces broker/worker infrastructure, distributed consistency, more deployment units,
     and operational complexity that conflicts with the current shared two-container MVP contract.
   - Effort: High

3. **Prompt-driven super-agent over existing chat endpoints** — give one Supervisor LLM the business
   rules and let it call the three conversational endpoints until it considers the analysis complete.
   - Pros: Fastest prototype and minimal initial refactoring.
   - Cons: State and validation authority become prompt-dependent; specialist outputs remain
     heterogeneous; retries are hard to make idempotent; evidence lineage and Judge independence are
     weak; internal HTTP calls add no useful boundary inside the modular monolith.
   - Effort: Medium

### Recommendation

Use approach 1. Define a `RevenueAnalysisRun` aggregate owned only by the Supervisor and an
append-only event stream. A run should bind `dataset_revision`, `ruleset_revision`, `as_of_date`,
phase states, attempts, normalized outputs, Judge verdicts, analyst annotations, provider metadata,
latency, token usage, and evidence references. Specialist agents remain deterministic executors;
OpenCode only selects from closed tools and produces bounded interpretations.

The nominal sequence should be `Billing -> Judge -> Collections -> Judge -> BI -> Judge ->
Completed`. Each specialist should return a shared envelope with `status`, `validation_checks`,
`findings`, `evidence_refs`, `data_quality`, `recommended_actions`, and execution metadata. The Judge
should combine mandatory deterministic checks with an independent model rubric. A failed hard check
must never be overridden by the LLM. A retry must reuse the same run/phase idempotency key, be bounded,
and end in `MANUAL_REVIEW` rather than loop indefinitely.

Business questions should first be captured as structured intent plus bounded free text: global
cut-off date and scope, then optional rules per specialist. A planning step may translate those rules
into approved tool calls, but the plan must be schema-validated before execution. Analyst verification
should be an auditable annotation/sign-off over immutable phase outputs; it should not block the
normal autonomous path unless the Judge emits `MANUAL_REVIEW` or the business explicitly requires a
human gate.

Implement persistence behind a repository interface so tests can use memory while K3S uses a durable
store. The existing architecture already proposes PostgreSQL for cases, tasks, approvals, and audit;
adding a queue or separate agent pods is not required for the first version. The API can initially run
the sequential workflow as a bounded background task and expose polling; server-sent events can be
added later without changing the domain model.

### Risks

- The six CSV files are currently retained only in RAM, so a durable run cannot resume after restart
  unless dataset revisions or their recoverable object references are persisted as well.
- Existing tool contracts answer one query at a time. Autonomous coverage requires a defined minimum
  tool bundle or an accepted plan contract; free-form rules alone cannot prove analysis completeness.
- A model-only Judge would merely add a second nondeterministic opinion. Deterministic invariants and
  evidence coverage must be authoritative, with the LLM limited to rubric-based qualitative review.
- Billing, Collections, and BI use different result shapes and status vocabularies; passing raw
  responses between phases would create brittle coupling and possible prompt injection through data.
- Automatic retries can duplicate expensive model calls or overwrite evidence unless phase writes are
  idempotent and append-only.
- Running work in FastAPI process memory is vulnerable to pod restarts and multi-worker duplication;
  the production execution ownership strategy must be explicit before claiming restart safety.
- The requested autonomy may conflict with earlier human approvals for financial actions. Analysis can
  be autonomous, but invoice issuance or payment application must remain simulated/read-only unless
  explicitly re-authorized.

### Ready for Proposal

No. The codebase supports the recommended architecture, but the following product decisions are not
inferable and materially change the specification:

1. Is the fixed sequence exactly Billing, then Collections, then BI, with the Judge allowed to stop or
   retry a phase but never reorder or skip it?
2. Are business rules entered as one global questionnaire, separate questions per specialist, or both;
   and which fields besides `as_of_date` are mandatory before automatic execution?
3. Is analyst verification non-blocking sign-off after each successful phase, or must the run pause for
   analyst approval before the next phase? The recommended default is non-blocking except on a Judge
   `MANUAL_REVIEW` verdict.
4. What authority should the Judge have: pass, one bounded retry, or manual-review only; and should it
   use the same OpenCode model or a separately configured model/rubric?
5. Must runs and uploaded datasets survive K3S pod restarts in this increment? If yes, confirm the
   approved durable storage boundary (the documented target is PostgreSQL plus object storage).
6. Does “autonomous” remain analysis-only, with no real invoice issuance, payment application, customer
   contact, or other external side effect?
