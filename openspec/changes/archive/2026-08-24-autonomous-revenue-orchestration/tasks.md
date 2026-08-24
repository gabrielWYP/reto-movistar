# Tasks: Autonomous Revenue Orchestration

## Review Workload Forecast

Estimated changed lines: 2,400–3,200; delivery: `ask-on-risk`.

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit/PR | Goal | Test | Harness | Rollback |
|---|---|---|---|---|
| A/app1 | Contracts/repository | `cd back && pytest tests/unit/test_orchestration_domain.py` | N/A: pure domain | domain/interfaces |
| B/app2 | Durable intake | `cd back && pytest tests/integration/test_sqlite_intake.py` | temp storage | intake/storage |
| C/app3 | Judge/adapters | `cd back && pytest tests/unit/test_judge.py tests/unit/test_specialist_adapters.py` | stubs | Judge/adapters |
| D/app4 | Runner/recovery | `cd back && pytest tests/integration/test_run_recovery.py` | restart/owners | runner/leases |
| E/app5 | API/review | `cd back && pytest tests/integration/test_run_api.py` | TestClient | routes |
| F/app6 | Supervisor UI | `cd back && pytest tests/integration/test_supervisor_ui.py` | browser smoke | frontend |
| G/app7 | Hardening/E2E | `cd back && pytest tests/end_to_end/test_autonomous_run.py` | Compose/curl | hardening/docs |
| H/infra | PVC/backup | `kubectl kustomize Movistar` | restore drill | manifests/PVC retained |

Selected Feature Branch Chain: app1 targets a draft tracker; each later app PR targets its predecessor. Keep each near 400 lines/60 minutes. H is a separate dependent `K3S_Infra` PR.

## Phase 0: Pre-apply Gates

- [x] 0.1 Record PV hostname/path/capacity, backup target/retention, and RPO/RTO before H.
- [x] 0.2 Select trusted analyst identity and immutable audit fields before E.

## Phase 1: Domain and Intake

- [x] 1.1 RED: add `back/tests/unit/test_orchestration_domain.py` for immutable contracts and out-of-order rejection (Runs/Fixed sequence).
- [x] 1.2 GREEN: create `domain/orchestration.py`, `persistence/repository.py`; REFACTOR invariants/docs.
- [x] 1.3 RED: add `back/tests/integration/test_sqlite_intake.py` for all Rule Intake scenarios.
- [x] 1.4 GREEN: implement `persistence/sqlite.py`, durable `application/dataset_supervisor.py`, config, atomic files, profiles/rulesets; REFACTOR transactions/docs.

## Phase 2: Judge and Specialists

- [x] 2.1 RED: add `back/tests/unit/test_judge.py` for all Judge scenarios.
- [x] 2.2 GREEN: implement `application/judge.py`; REFACTOR deterministic-first rubric/provider metadata/docs.
- [x] 2.3 RED: add `back/tests/unit/test_specialist_adapters.py` for bound inputs, read-only tools, normalized lineage, handoffs.
- [x] 2.4 GREEN: implement `application/specialist_adapters.py` and registry/specialist wiring; REFACTOR envelopes/docs.

## Phase 3: Runner and Recovery

- [x] 3.1 RED: add `back/tests/integration/test_run_recovery.py` for all Runs recovery/idempotency/ownership scenarios.
- [x] 3.2 GREEN: implement `application/orchestrator.py`: leases, digests, transitions, resume, background runner.
- [x] 3.3 REFACTOR: add `persistence/backup.py`, quarantine/readiness freeze, package assembly, corruption/lineage tests/docs.

## Phase 4: API, UI, Review

- [x] 4.1 RED: add `back/tests/integration/test_run_api.py` for Runs/Final Review API scenarios.
- [x] 4.2 GREEN: create `entrypoints/run_api.py`; wire `api.py`, identity, conflicts/review routes; REFACTOR OpenAPI docs.
- [x] 4.3 RED: add `back/tests/integration/test_supervisor_ui.py` for intake→progress→Judge→one decision and read-only tabs.
- [x] 4.4 GREEN: replace demo in `front/index.html`, `assets/app.js`, `assets/app.css`; REFACTOR accessible polling/manual-review/docs.

## Phase 5: Operations

- [x] 5.1 RED: add `back/tests/end_to_end/test_autonomous_run.py` for upload security, corruption, prompt exclusion, readiness, telemetry, lineage.
- [x] 5.2 GREEN: harden limits/logging/docs; run pytest, Ruff, Mypy, format, Compose checks.
- [x] 5.3 Infra RED/GREEN: validate then add retained PV/PVC, UID/GID 1001 mount, one `Recreate` backend, affinity, backup/restore under `K3S_Infra/Movistar`.
- [x] 5.4 Verify K3S: six-CSV run, retry, restart, restore, analyst decision, no external effect.

## Phase 6: Live Readiness Remediation

- [x] 6.1 RED/GREEN: require one stable digest confirmation retry for `REQUIERE_VALIDACION`; changed evidence escalates to `MANUAL_REVIEW`.
- [x] 6.2 RED/GREEN: add a checksummed one-shot operator checkpoint on the durable PVC and resume without duplicate steps after restart.
- [x] 6.3 Wire the required `ANALYST_HTPASSWD` secret into the reusable K3S deploy and verify unauthenticated public access is denied.
- [x] 6.4 Merge the remediation chain, deploy the immutable release, and complete live task 5.4 evidence.

## Phase 7: Final Verification Remediation (Issue #57)

- [x] 7.1 RED/GREEN: persist trusted evidence annotations separately and prove direct final-review replay/conflict without run mutation or rerun.
- [x] 7.2 RED/GREEN: refuse already-bound external-effect rules inside every specialist adapter before any tool invocation and emit fail-closed evidence.
