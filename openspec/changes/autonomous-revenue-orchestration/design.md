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

## Persistence, Recovery, and Contracts

`/var/lib/sonia` contains `db/sonia.sqlite3`, `datasets/<revision>/<sha256>.csv`,
`evidence/<run>/<phase>/<attempt>/<sha256>.json`, and `packages/<revision>.json`. Writes use a same-directory
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

Uploads remain six allow-listed CSV/ZIP sources, 25 MiB maximum, bounded rows/fields, validated encoding/schema;
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

- [ ] Confirm local-PV node hostname/path, capacity, backup destination, retention, and restore RPO/RTO.
- [x] Trust the proxy/SSO `X-Forwarded-User` claim; ingress strips client values and overwrites this header.
