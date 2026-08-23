# Apply Progress: Autonomous Revenue Orchestration

## Cumulative Status

- Mode: Strict TDD; delivery: Feature Branch Chain.
- Completed: 1.1-2.4 (8/21); remaining: gates 0.1-0.2 and tasks 3.1-5.4.
- Current branch: `feature/autonomous-revenue-orchestration-03-judge-adapters`.
- Intended base: `feature/autonomous-revenue-orchestration-02-intake`.

## TDD Cycle Evidence

| Tasks | RED | GREEN | Triangulate | Refactor |
|---|---|---|---|---|
| 1.1-1.2 | `/home/linuxbrew/.linuxbrew/bin/python3 -m pytest tests/unit/test_orchestration_domain.py`: collection failed, missing `sonia.domain.orchestration` | `.venv-py312/bin/python -m pytest back/tests/unit/test_orchestration_domain.py`: 6 passed | Happy fixed sequence plus early Collections, non-PASS, attempt, immutability, telemetry, and port cases | Extracted frozen base and transition tables; 6 passed |
| 1.3-1.4 | Initial collection failed without `sqlite`; correction RED: delete command left 1 failed/4 passed | Focused GREEN: 5 passed | Valid/incomplete, replay/conflict, typed/required/revised rules, issue/delete effects | Reopened SQLite from `tmp_path`; 5 passed |
| 2.1-2.4 | Collection failed without modules; lineage correction: 1 failed/1 passed | GREEN: 5 passed; lineage correction: 2 passed | PASS/hard failure, retry/manual, fallback, history, bound run/attempt/tool evidence | Simplified evidence normalization; focused green |

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

## Work Unit A/app1

Start: design-only tracker branch. End: immutable execution, result, Judge, run contracts;
fixed legal transitions; optimistic append-only repository port. No SQLite, intake, API, UI,
Judge implementation, adapters, runner, or infrastructure is included.

Files changed: `back/src/sonia/domain/orchestration.py`,
`back/src/sonia/persistence/repository.py`, `back/tests/unit/test_orchestration_domain.py`,
`tasks.md`, and this progress artifact. Deviations from design: none.

Work Unit B/app2 ends with durable, checksummed dataset/profile/question/ruleset intake; API wiring and orchestration remain deferred.
Work Unit C/app3 ends with deterministic-first Judge gates and fixed in-process specialist adapters; runner persistence remains deferred.
