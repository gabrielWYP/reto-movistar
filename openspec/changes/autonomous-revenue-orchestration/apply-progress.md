# Apply Progress: Autonomous Revenue Orchestration

## Cumulative Status

- Mode: Strict TDD; delivery: Feature Branch Chain.
- Completed: 23/25 tasks; remaining: live K3S 5.4 and remediation deployment 6.4.
- Current branch: `feature/autonomous-revenue-orchestration-15-deploy-auth`.
- Intended base: `feature/autonomous-revenue-orchestration-14-operator-checkpoint`.

## TDD Cycle Evidence

| Tasks | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|
| 1.1-1.2 | `/home/linuxbrew/.linuxbrew/bin/python3 -m pytest tests/unit/test_orchestration_domain.py`: collection failed, missing `sonia.domain.orchestration` | `.venv-py312/bin/python -m pytest back/tests/unit/test_orchestration_domain.py`: 6 passed | Happy fixed sequence plus early Collections, non-PASS, attempt, immutability, telemetry, and port cases | Extracted frozen base and transition tables; 6 passed |
| 1.3-1.4 | Initial collection failed without `sqlite`; correction RED: delete command left 1 failed/4 passed | Focused GREEN: 5 passed | Valid/incomplete, replay/conflict, typed/required/revised rules, issue/delete effects | Reopened SQLite from `tmp_path`; 5 passed |
| 2.1-2.4 | Collection failed without modules; lineage correction: 1 failed/1 passed | GREEN: 5 passed; lineage correction: 2 passed | PASS/hard failure, retry/manual, fallback, history, bound run/attempt/tool evidence | Simplified evidence normalization; focused green |
| 3.1-3.2 | Missing module; correction RED: retry-then-pass exceeded bound 8 | GREEN: 4 passed; correction passed with bound 13 | Replays/conflicts, sequence, restart, owners, retry/pass, retry/manual, storage loss | Compact transactional runner; focused green |
| 3.3 | Missing symbols; correction REDs covered backup/reason, terminal auto-package, reopen and repeated-direct version drift | Storage 6 passed; package 5 passed in 1.98s | Exact backup, corrupt freeze, durable reason/version idempotency, automatic terminal packages, explicit corruption harness | Formatted split; combined 21 passed |
| 0.2, 4.1-4.2 | Initial 4 failed without wiring; app8 RED: 2 failed without `storage_root` | Core router/DI plus production composition GREEN: 6 focused passed | Durable intake/run/reopen, dynamic adapters, evidence/review reads, whitespace fail-closed | Shared helpers and immutable typed responses; combined 11 passed |
| 4.3-4.4 | UI RED: 1 failed/1 passed without autonomous controls | Focused GREEN: 3 passed | Static accessibility/read-only boundary plus real six-step terminal API journey | Removed runtime demo calls; Node syntax and focused regression passed |
| 5.1-5.2 | Import RED; triangulation 2 failed/6 passed; review REDs: 2 failed then physical-row 1 failed | Focused GREEN: 12 passed | CSV/ZIP limits, localized negatives, sanitized 503, prompt exclusion, lineage and telemetry | Preserved one safe ZIP wrapper, bounded nesting, fixed recovery semantics; combined 32 passed |
| 0.1, 5.3 | Safety net rendered 2 Deployments/2 Services; RED failed `missing: name: sonia-live`; restore correction RED rejected `/unused-live` lineage anchor | Storage contract GREEN; Kustomize and 13-resource kubeconform pass | Live/backup PVs, Recreate/readiness, exact retention boundary, fresh restore target, unchanged front | Direct operation-file checks and CI schema validation for the non-rendered restore template |
| Slice A / 5.4 prerequisite | Unit RED: 1 failed/3 passed because `Judge.evaluate` lacked prior-result confirmation; integration triangulation caught an upstream-evidence false match | Focused Judge/adapters/recovery: 12 passed; proportional regression: 35 passed | Stable Billing digest completes with eight steps; changed digest enters MANUAL_REVIEW after four steps/two attempts | Output selection now binds phase and attempt before comparing digests; 5.4 remains pending live verification |
| 6.2 / Slice B | Checkpoint RED: 6 failed; active-start RED returned stale `BILLING_RUNNING`, and router harness exposed missing state wiring | Focused checkpoint/router: 7 passed; recovery: 12 passed | One-shot pause/restart plus corrupt, symlink, cross-run, invalid digest and illegal state freeze | Extracted typed checkpoint store; atomic audit rename/fsync and lease release preserve restart boundary |
| 6.3 / Slice C | Contract RED: 1 failed because the reusable deploy caller forwarded no analyst roster | Focused contract: 1 passed | Exact required secret mapping is present once under the reusable deploy job | Caller-only passthrough; roster reconciliation and BasicAuth enforcement remain owned by K3S Infra |
| Issue #54 recovery remediation | Direct production-composition RED: 1 failed because recreated registries were empty | Focused GREEN: 1 passed; proportional recovery/intake/adapters: 20 passed | A newer publication is restored at startup, then the paused run atomically reactivates its older bound revision and completes eight exact steps | Added checksummed durable reads and a shared revision-scoped execution boundary; TestClient baseline timed out, direct app-state harness passed |

## Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused tests | `.venv-py312/bin/python -m pytest back/tests/unit/test_orchestration_domain.py`: 6 passed in 0.85s |
| Runtime harness | N/A: this slice contains pure domain contracts and repository protocols, with no runtime adapter or I/O boundary. |
| Ruff | `.venv-py312/bin/ruff check ...` and `ruff format --check ...`: all checks passed; 3 files already formatted. |
| Mypy | `cd back && ../.venv-py312/bin/mypy src/sonia/domain/orchestration.py src/sonia/persistence/repository.py`: success, no issues in 2 files. |
| Rollback | Remove the three new Python files and revert only task checkboxes 1.1-1.2. |
| B/app2 | Focused/runtime: real SQLite + temporary filesystem, 5 passed; combined Supervisor regression: 9 passed; Ruff/format/Mypy/diff passed. Rollback: remove `sqlite.py` and its test, revert the optional coordinator dependency and tasks 1.3-1.4. |
| C/app3 | Combined: 11 passed. Runtime `.venv-py312/bin/python -c '<fixture six-CSV adapter harness>'` loaded real services with `back/tests/fixtures/supervisor`: `[('billing', 'REQUIERE_VALIDACION', 3, 'billing_health_snapshot'), ('collections', 'RESULT_AVAILABLE', 6, 'portfolio_snapshot'), ('bi', 'RESULT_AVAILABLE', 9, 'executive_snapshot')]`. Ruff/format/Mypy/diff passed. Rollback: remove Judge/adapters/tests, revert JudgeDecision metadata/time and tasks 2.1-2.4. |
| D/app4 | Focused: 4 passed in 2.18s; combined regression: 20 passed in 2.58s. Runtime restart/competing-owner harness: 1 passed in 1.20s. Ruff/format/Mypy/diff passed. Rollback: remove `orchestrator.py` and its integration test; revert tasks 3.1-3.2. Task 3.3 remains pending as a complete child slice. |
| E/app5-storage partial | Focused 5 passed in 2.06s; combined 25 passed in 3.74s; runtime backup→restore + corruption/start freeze 2 passed in 1.44s. Ruff/format/Mypy/diff passed. Rollback: remove `backup.py`, test and runner guard; task 3.3 stays open. |
| F/app6-package | Focused 5 passed in 1.98s; combined 21 passed in 3.42s. Runtime autonomous completed+manual packages: 2 passed in 1.34s. Ruff/format/Mypy/diff passed. Rollback: remove package validator/assembler, auto-trigger/escalation/manual reason and package test; reopen 3.3. |
| G/app7-run-api partial | Focused `.venv-py312/bin/pytest -q -s back/tests/integration/test_run_api.py`: 4 passed; combined durable: 24 passed; final Supervisor/API regression: 14 passed; TestClient harness `.venv-py312/bin/pytest -q -s back/tests/integration/test_run_api.py::test_completed_review_is_append_only_and_digest_idempotent`: 1 passed. Core router/DI/review store is proven; production composition, dataset/questions/ruleset routes and evidence content/review retrieval move to the immediate child slice. Ruff/format/Mypy/diff passed. Rollback: remove `run_api.py`/test, revert optional `api.py` injection and 0.2/4.1. |
| H/app8-production-composition | Focused TestClient: 2 passed; combined API/Supervisor regression: 11 passed. Runtime flow published six CSVs, created rules/run, completed all six steps, read package/evidence/review, then reopened SQLite successfully. Ruff/format/Mypy/diff passed. Rollback: revert default composition, intake/evidence/review routes, storage setting/Docker ownership, test, design decision and task 4.2. |
| I/app9-supervisor-ui | Focused/runtime `.venv-py312/bin/pytest -q -s back/tests/integration/test_supervisor_ui.py`: 3 passed, including real dataset→rules→202 start→COMPLETED with six evidence records; `node --check front/assets/app.js` passed. Chromium snap could not reach the WSL-local server, so no browser claim is made. Rollback: revert the three Supervisor frontend files, remove the UI test, reopen 4.3-4.4. |
| J/app10-hardening-e2e | Focused/runtime `.venv-py312/bin/pytest -q -s back/tests/end_to_end/test_autonomous_run.py`: 12 passed; real app completed six steps/package and ASGI readiness returned 503 after dataset corruption. Combined non-TestClient regression: 32 passed. Ruff/format/Mypy/Compose/diff passed. Rollback: remove E2E test and revert validation, `/ready`, upload-path and orchestration-log changes; reopen 5.1-5.2. |
| K/app11-k3s | Focused `bash Movistar/tests/validate-autonomous-storage.sh`: PASS; `kubectl kustomize Movistar`: 2 Deployments, 2 Services, 2 PVs, 2 PVCs, 1 CronJob; kubeconform: 13 valid/0 invalid/0 errors; PyYAML 12 files and both repos `git diff --check` passed. Live `kubectl get nodes --request-timeout=5s` blocked: `127.0.0.1:6443 was refused`, so 5.4 remains open. Rollback: revert app design/tasks/progress and infra storage/operations/workload/kustomization/workflow files; retained PV data must be preserved/exported, not deleted. |
| L/app13-retry-confirmation | Focused 12 passed; combined Judge/adapters/recovery/package/storage/E2E 35 passed. Real six-CSV runtime completed eight ordered steps with Judge verdicts Billing RETRY/PASS, Collections PASS, BI PASS and a valid package. Ruff/format/Mypy/diff passed; TestClient composition remains subject to the documented WSL/OneDrive stall. Rollback: revert Judge prior-result gate, orchestrator binding, retry tests/docs; task 5.4 stays open. |
| M/app14-operator-checkpoint | Focused checkpoint/direct-router harness: 7 passed; isolated proportional regression: 42 passed (recovery 12, Judge/adapters/package/storage 17, E2E 12, direct router 1). Runtime paused after committed Billing, atomically archived one request, reopened with a new owner, replayed start from `BILLING_JUDGING`, and completed with Billing called once. Invalid requests froze before any specialist call. HTTP TestClient transport stalled and was replaced by the direct real router harness. Ruff/format/Mypy/diff passed. Rollback: remove `operator_checkpoint.py`, revert runner/start hooks, tests/docs and reopen 6.2; 5.4 stays open. |
| N/app15-deploy-auth | Focused `.venv-py312/bin/pytest -q -s back/tests/integration/test_deploy_auth_contract.py`: 1 passed. Workflow YAML/action syntax and diff passed. Runtime deployment is deferred to 6.4; K3S Infra declares the secret required and reconciles its BasicAuth roster. Rollback: remove only the caller mapping/test and reopen 6.3. |
| O/issue-54-recovery | Focused direct harness: 1 passed; combined direct regression: 20 passed. Recreated `create_app` over the same root restored all registries, resumed from Billing attempt 1, completed eight rows with Judge `RETRY/PASS/PASS/PASS`, and did not duplicate attempt 1 even when a newer dataset existed. Ruff/format/Mypy/diff passed. Rollback: revert repository reads, coordinator revision scope, production composition wiring, recovery test and this design note; 5.4/6.4 remain open. |

## Work Unit A/app1

Start: design-only tracker branch. End: immutable execution, result, Judge, run contracts;
fixed legal transitions; optimistic append-only repository port. No SQLite, intake, API, UI,
Judge implementation, adapters, runner, or infrastructure is included.

Files changed: `back/src/sonia/domain/orchestration.py`,
`back/src/sonia/persistence/repository.py`, `back/tests/unit/test_orchestration_domain.py`,
`tasks.md`, and this progress artifact. Deviations from design: none.

Work Unit B/app2 ends with durable, checksummed dataset/profile/question/ruleset intake; API wiring and orchestration remain deferred.
Work Unit C/app3 ends with deterministic-first Judge gates and fixed in-process specialist adapters; runner persistence remains deferred.
Work Unit D/app4 ends with durable digest-bound run sequencing, bounded retries, recovery, and expiring single-owner leases; backup/quarantine/package assembly remains deferred to 3.3.
Work Unit E/app5-storage is partial: verified backup/restore, fail-closed start/advance readiness, and symlink-aware orphan quarantine; package assembly moves to a bounded child slice and 3.3 remains open.
Work Unit F/app6-package closes 3.3 with checksummed completed/manual packages and fail-closed lineage escalation; analyst decisions remain deferred.
