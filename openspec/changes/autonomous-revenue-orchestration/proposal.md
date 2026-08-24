# Proposal: Autonomous Revenue Orchestration

## Intent

Replace three independent chatbots with one autonomous, evidence-first run. After Supervisor
publishes six CSVs, the analyst answers global and specialist questions; the system executes Billing,
Collections, and BI sequentially, then presents one final output.

## Scope

### In Scope
- Durably version datasets, profiles, rules, runs, evidence, and audit events.
- Derive global and specialist questions from CSV profiles and compile a typed plan.
- Execute `Billing -> Judge -> Collections -> Judge -> BI -> Judge` without analyst stage gates.
- Normalize validations; enforce `PASS`, one `RETRY`, then `MANUAL_REVIEW`.
- Expose progress, Judge evidence, final package, and analyst sign-off.

### Out of Scope
- External financial effects, including issuance, payment application, or customer contact.
- Reordering/skipping specialists, horizontal scaling, brokers, workers, or SSE.

## Capabilities

### New Capabilities
- `supervisor-rule-intake`: Profiling, revisions, and global/specialist rules.
- `revenue-analysis-runs`: Fixed sequencing, persistence, recovery, and idempotency.
- `specialist-judge-gates`: Hard checks, model rubric, retry, and escalation.
- `analyst-final-review`: Consolidated evidence, annotations, and sign-off.

### Modified Capabilities
None; no main specifications exist yet.

## Approach

Add a typed `RevenueAnalysisRun` state machine and append-only repository within the shared backend.
Specialists use in-process adapters; hard deterministic checks override LLM judgments. The MVP stores
SQLite and immutable datasets on one RWO PVC, preserving two application containers and one backend
replica. It requires atomic file replacement, disciplined SQLite WAL/locking, checksummed backups,
and verified recovery. Rollout must prevent pod overlap (`Recreate` or zero surge), mount a UID/GID
1001-writable path, and respect static `local-storage` provisioning, node affinity, and `Retain`.
SQLite/file persistence explicitly prohibits horizontal backend scaling.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `back/src/sonia/` | Modified/New | Orchestration, persistence, API, adapters, audit. |
| `front/` | Modified | Rules, progress, Judge evidence, final review. |
| `back/tests/` | Modified/New | Sequence, retry, recovery, lineage, idempotency. |
| `K3S_Infra/Movistar/` | Modified later | PV/PVC, mount, rollout, backups. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Duplicate work after failure | Medium | Idempotency keys; append-only transitions. |
| Local-PV node loss | Medium | Retained PV; verified backups. |
| Invalid model verdict | Medium | Hard gates override the rubric. |

## Rollback Plan

Disable run creation, restore current read-only specialist routes, roll back manifests, and retain or
export the PVC for audit.

## Dependencies

- K3S static `local-storage` capacity and backup destination.
- OpenCode planning/Judge configuration with deterministic fallback.

## Success Criteria

- [ ] A recoverable run never skips Judge gates.
- [ ] Restart preserves datasets and audit history.
- [ ] Analyst validates one immutable final package.
- [ ] Autonomous actions remain read-only and CSV-traceable.
