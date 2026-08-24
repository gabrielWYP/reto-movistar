# Design: Autonomous Revenue Orchestration

## Technical Approach

The shared FastAPI backend owns `RevenueAnalysisRun`, invokes specialists in-process, and durably records
inputs, transitions, results, verdicts, and review. The browser performs intake, polling, and final validation.

## Architecture Decisions

| Decision | Choice and rationale | Rejected alternative |
|---|---|---|
| Orchestration | Central state machine makes ordering, retries, and recovery testable. | Prompt super-agent/broker: weak invariants/excess infrastructure. |
| Storage | SQLite plus immutable files on one RWO PVC fits one replica and transactional audit. | Memory cannot recover; PostgreSQL/object storage waits for scaling. |
| Execution | One FastAPI background runner with durable lease and polling. | Internal HTTP duplicates boundaries; SSE is deferred. |
| Judge | Hard gates precede an independent model rubric, preserving evidence authority. | Model-only judgment. |

The local-PV operating contract is fixed to node `gabo-vm-arm`, storage class `local-storage`,
`/mnt/tesis_data/movistar` (5Gi live) and `/mnt/tesis_data/movistar-backups` (10Gi backup).
Backups run daily with 14-day retention; objectives are RPO 24h and RTO 4h. Both volumes are
node-local: they do not protect against node or disk loss, so off-node replication remains a
production-hardening follow-up.

## Data Flow

```mermaid
sequenceDiagram
  participant A as Analyst/Supervisor UI
  participant O as Orchestrator
  participant S as SQLite + immutable files
  participant B as Billing adapter
  participant C as Collections adapter
  participant I as BI adapter
  participant J as Judge
  A->>O: upload six CSVs (idempotency key)
  O->>S: validate, profile, checksum, publish dataset revision
  O-->>A: global + Billing/Collections/BI questions
  A->>O: answers; create immutable ruleset and start run
  O->>B: typed plan
  B-->>J: normalized Billing result
  J-->>O: Billing verdict
  O->>C: plan + approved Billing evidence
  C-->>J: normalized Collections result
  J-->>O: Collections verdict
  O->>I: plan + approved upstream evidence
  I-->>J: normalized BI result
  J-->>O: BI verdict
  O->>S: atomic outputs, verdicts, transitions, audit
  O->>S: immutable final/manual-review package
  A->>O: accept/reject package
  O->>S: append analyst validation
```

Only the orchestrator mutates state. Legal states are `CREATED -> BILLING_RUNNING ->
BILLING_JUDGING -> COLLECTIONS_RUNNING -> COLLECTIONS_JUDGING -> BI_RUNNING -> BI_JUDGING ->
COMPLETED`; a first retryable verdict returns only to the same phase, and any terminal failure enters
`MANUAL_REVIEW`. Commands bind idempotency key to digest. `BEGIN IMMEDIATE` renews
`lease_owner/lease_expires_at`; competing owners are read-only.

`REQUIERE_VALIDACION` is a retryable deterministic confirmation gate: attempt one emits RETRY;
attempt two may PASS only when the current phase/attempt output evidence digest is identical to
attempt one. Changed or missing evidence escalates to MANUAL_REVIEW, preserving the two-attempt bound.

Operator-controlled restart verification uses no endpoint or timer. A canonical
`checkpoints/<run_id>.request.json` envelope binds schema, request ID, run ID, legal target state, and
SHA-256. Before each advance, `run()` validates the fixed contained path and consumes a matching target
with atomic rename into `checkpoints/consumed/<digest>.json`, fsyncs both directories, releases its lease,
and returns the committed snapshot. Corrupt, symlinked, cross-run, invalid-digest, stale, or illegal-state
requests remain in place and freeze advancement. Replaying `POST /start` on an active run returns the
current snapshot and schedules continuation from its durable version without duplicating committed steps.

## Persistence, Recovery, and Contracts

`/var/lib/sonia` contains `db/sonia.sqlite3`, `datasets/<revision>/<sha256>.csv`,
`evidence/<run>/<phase>/<attempt>/<sha256>.json`, `checkpoints/`, and `packages/<revision>.json`. Writes use a same-directory
temporary file, `fsync`, checksum, then rename. One transaction records reference, snapshot, event, and
idempotency result; orphaned files are quarantined. Startup verifies checksums, expires leases, and resumes
from the last commit. Missing/corrupt storage fails readiness, freezes runs, and requires operator recovery.

Pydantic contracts are immutable `ExecutionPlan`, `SpecialistResult(status, validation_checks, findings,
evidence_refs, data_quality, recommended_actions, metadata)`, and `JudgeDecision(verdict, hard_checks,
rubric, corrective_constraints, mode, evidence_refs)`. Adapters call Billing, Collections, and BI Python
services directly. Hard checks run first; `SONIA_JUDGE_MODEL` separately selects `deepseek-v4-flash` under
the existing `OPENCODE_KEY` contract. Provider failure invokes deterministic fallback. Logs/metrics include
`run_id`, dataset revision, phase, attempt, verdict, latency, tokens, lease, and recovery outcome.

## API and UI

`POST /api/supervisor/datasets`, `GET /api/supervisor/datasets/{revision}/questions`,
`POST /api/supervisor/rulesets`, `POST /api/supervisor/runs`, `POST /api/supervisor/runs/{id}/start`,
`GET /api/supervisor/runs/{id}`, evidence retrieval, and package review use strict schemas/conflicts. Start returns `202`; polling
is authoritative. Only Supervisor exposes upload/rules; specialist tabs stay read-only. UI renders history,
limitations, the final package, and one analyst decision.

## Security and File Changes

Uploads remain six allow-listed CSV/ZIP sources, 25 MiB maximum, 250,000 data rows per source and
256 fields per row, with validated encoding/schema;
traversal/symlinks, absolute paths, duplicates, formulas, and unsupported instructions are rejected.
Server IDs and resolved containment prevent path injection. Evidence is append-only/checksummed; raw rows
never reach prompts. Secrets remain Kubernetes Secrets; tools are read-only.

| Files | Action |
|---|---|
| `back/src/sonia/{domain/orchestration.py,application/orchestrator.py,application/judge.py,application/specialist_adapters.py,persistence/repository.py,persistence/sqlite.py,persistence/backup.py,entrypoints/run_api.py}` | Create |
| `back/src/sonia/{application/dataset_supervisor.py,application/agent_registry.py,entrypoints/api.py,config.py}`; `Agente Cobranzas/BACK/src/collections_agent/application.py`; `Agente BI/BACK/src/bi_agent/{application.py,integration.py}`; `front/{index.html,assets/app.js,assets/app.css}` | Modify |
| `back/tests/{unit,integration,end_to_end}/` | Add state, Judge, idempotency, restart, corruption, lineage, API/UI tests. |
| `K3S_Infra/Movistar/00-storage/{pv,pvc}.yaml`, `03-workloads/back-deployment.yaml`, `05-operations/backup-cronjob.yaml`, `kustomization.yaml` | Add `local-storage`, `Retain`, node affinity, backup/restore, and UID/GID 1001 mount. |

## Threat Matrix

| Boundary (adversarial cases) | Applicability | Response | RED tests |
|---|---|---|---|
| Documentation-like paths (`requirements.txt`, `CMakeLists.txt`, executable MDX/Markdown, `README.sh`) | N/A: no executable-file classification | Uploads are data-only. | None |
| Git repository selection (`git -C`, relative/absolute paths) | N/A: runtime invokes no Git | No cwd authority. | None |
| Commit state (staged, `commit -a`, empty index) | N/A: no VCS automation | No index/worktree semantics. | None |
| Push state (tracking, first push, refspec) | N/A: no VCS automation | No ref destination. | None |
| PR commands (`--head`, environment prefix, composed commands) | N/A: no PR automation | No command composition. | None |

## Testing and Rollout

Strict TDD covers domain/contracts/adapters; SQLite/API integration covers restart; container E2E verifies
sequence, one retry, PVC persistence, backup restore, and pod restart.
Deploy PV/PVC first, then change only backend to `Recreate` (replacing `maxSurge: 1`), one replica/worker,
RWO mount, readiness storage check; front remains the second workload. Rollback disables run creation and
restores the prior image while retaining/exporting the PVC.

## Open Questions

- [x] Local PV contract: `gabo-vm-arm`, paths/capacities above, daily/14 days, RPO 24h/RTO 4h.
- [x] Trust the proxy/SSO `X-Forwarded-User` claim; ingress strips client values and overwrites this header.
