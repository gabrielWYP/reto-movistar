# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

SON-IA is a prototype for the AI Telecom Challenge (Desafío 3): a controlled orchestration
of three specialist agents — Billing (Facturación), Collections (Cobranzas/Recaudo) and BI —
behind one public entry point. Financial actions (invoice issuance, payment application,
customer contact) are simulated and gated by human approval; all calculations are
deterministic Python and only compact evidence reaches a language model.

Product docs are in Spanish (`README.md`, `docs/`, `business/`). Code, comments, identifiers
and specs are in English.

## Repository layout

Four independently installable Python packages, plus a shared frontend:

| Path | Package | Role |
| --- | --- | --- |
| `back/` | `sonia` | Shared FastAPI app, Supervisor, run orchestrator, Judge, persistence |
| `Agente_Facturacion/BACK/` | `billing_agent` | Billing specialist (also vendored under `back/src/sonia/agents/billing/`) |
| `Agente Cobranzas/BACK/` | `collections_agent` | Collections specialist + its own front |
| `Agente BI/BACK/` | `bi_agent` | BI specialist + its own front |
| `front/` | — | Supervisor UI, static assets, Nginx config |

Each `Agente */` folder also carries its own `FRONT/`, `DEPLOY/kubernetes/` and `compose.yaml`
so the agent can be run standalone; the integrated build composes all of them into two images.

Non-code assets: `business/` (process rules, YAML acceptance criteria, CSV cases),
`data/synthetic/` (fictitious datasets only), `evals/`, `docs/`, `openspec/`.

## Development commands

Reference interpreter is Python 3.12 (same as CI). One venv covers all four packages:

```bash
uv venv --python 3.12 .venv-py312
uv pip install --python .venv-py312/bin/python \
  --editable './Agente BI/BACK[dev]' \
  --editable './Agente Cobranzas/BACK[dev]' \
  --editable './Agente_Facturacion/BACK[dev]' \
  --editable './back[dev]'
source .venv-py312/bin/activate
```

A pre-existing `.venv` built on Python 3.14 is **not** the validation reference.

Run the API (serves the frontend too):

```bash
python -m sonia            # http://localhost:8080
sonia-billing              # billing CLI entry point
```

Quality gates, per package — CI runs exactly these:

```bash
cd back && python -m ruff check src tests && python -m ruff format --check src tests
cd back && python -m mypy src
cd back && python -m pytest
cd "Agente BI/BACK" && python -m ruff check src tests && python -m mypy src && python -m pytest
cd "Agente Cobranzas/BACK" && python -m pytest
cd Agente_Facturacion/BACK && python -m pytest
```

Single test / coverage:

```bash
cd back && python -m pytest tests/unit/test_judge.py::test_name
cd back && python -m pytest --cov=sonia --cov-report=term-missing
```

The BI suite defines an `official_dataset` marker for regressions against the six official
hackathon CSVs (`-m official_dataset` / `-m 'not official_dataset'`).

Containers:

```bash
docker compose up --build --wait   # two pods: front (8080) + back
docker compose down --volumes
```

Production builds `front/Dockerfile` and `back/Dockerfile`. The root `Dockerfile` is a
single-image compatibility build kept for local use and the CI smoke test only.

## Architecture

### Single public entry, two containers

Only `front` is published. Nginx routes `/api/*` and `/health` to the `back` Service.
Both containers run read-only as UID/GID `1001:1001`. Frontend assets are cache-busted at
build time by replacing `__ASSET_VERSION__` with a hash of the asset tree — never ship an
`index.html` still containing that token, CI asserts against it.

`back/src/sonia/entrypoints/api.py::create_app` is the composition root. It mounts the three
specialist routers/apps into one FastAPI instance and takes every collaborator as an optional
constructor argument, so tests inject fakes instead of monkeypatching.

### Supervisor is the only dataset writer

`SupervisorDatasetCoordinator` (`application/dataset_supervisor.py`) validates a complete
six-CSV package and publishes it **atomically** to Billing, Collections and BI. If any agent
rejects the package, none of them change. Specialist upload endpoints are wired with
`allow_manual_upload=False` and answer **403** — specialist tabs are read-only with respect
to the data source. Before publication the coordinator rejects zip bombs, CSV formula
injection and unsafe upload names. Publication is idempotent through an `Idempotency-Key`
header.

State lives in RAM and is rehydrated from durable storage at startup
(`rehydrate_latest`); a pod restart without storage loses the dataset. Endpoints:
`GET|POST /api/supervisor/dataset` (compat) and `POST /api/supervisor/datasets` (revision-bound).

### Run orchestration: fixed order, Judge gates

`domain/orchestration.py` holds the immutable contracts — Pydantic models with
`extra="forbid", frozen=True`. Specialists always execute in one legal order:
`BILLING → COLLECTIONS → BI`. `RunState` walks `CREATED → *_RUNNING → *_JUDGING → … →
COMPLETED | MANUAL_REVIEW`.

`RunOrchestrator` (`application/orchestrator.py`) is a **single-owner durable runner**: it
leases a run (30s default), persists digest-bound commands and append-only steps into SQLite
(`runs`, `run_commands`, `run_steps`), and advances one run at a time. Retries are bounded;
exhaustion routes to `MANUAL_REVIEW`, never to a silent pass.

`Judge` (`application/judge.py`) is deterministic-first: hard gates run before any optional
qualitative model, with `JudgeMode` recording whether the verdict came from `deterministic`,
`model` or `fallback` evidence. A phase gets at most one retry: a failing check on attempt 1
yields `RETRY`, anything later yields `MANUAL_REVIEW`, and non-retryable checks skip straight
to it. Statuses that require confirmation must reproduce an identical output digest on
attempt 2 to pass. `external_effect_rule_ids` blocks rules that request real
external effects (issue invoice, apply payment, contact customer, delete — in Spanish and
English).

`SpecialistAdapter` (`application/specialist_adapters.py`) binds each phase to one fixed
read-only in-process operation — no HTTP, no prompt execution — and normalizes the output
into evidence references carrying an integrity digest and the dataset revision lineage.

`entrypoints/run_api.py` exposes the analyst surface under `/api/supervisor`: runs, history,
evidence, evidence annotations, evidence packages, and the immutable final review.

### Persistence and readiness

`persistence/sqlite.py` (intake), `persistence/backup.py` (`StorageHardener`, artifact
packaging and lineage) and `persistence/operator_checkpoint.py`. `SONIA_STORAGE_ROOT`
defaults to `/var/lib/sonia` in production and `/tmp/sonia` otherwise. Durable orchestration
is composed **only** when a storage root is configured; otherwise the run router is absent.
`GET /ready` fails closed with 503 when storage is unavailable or corrupt — keep it that way.

### AI runtime

BI and Collections call OpenCode Go with `deepseek-v4-flash` when `OPENCODE_KEY` is set.
The key never reaches the frontend and is never baked into an image. Absent a key, the agents
degrade to their deterministic paths.

## Conventions

- Ruff (line length 100, `select = ["E","F","I","B","UP","ANN"]`) and strict Mypy. The
  vendored `sonia.agents.billing` tree is excluded from both — do not "fix" it into scope.
- Blocking work belongs off the event loop: wrap synchronous coordinator/orchestrator calls
  in `run_in_threadpool`.
- Structured logging only, via `observability/logging.py`: `logger.info("event_name",
  extra={...})` with snake_case event names and no interpolated messages. Every request
  carries an `x-request-id`.
- Strict TDD is declared in `openspec/config.yaml`; tests and docs ship in the same work unit
  as the behavior they verify, and changes forecast a 400-changed-line review budget.
- `back/tests/` is layered: `unit/`, `integration/` (FastAPI TestClient), `end_to_end/` and an
  empty `contract/` placeholder, with shared CSVs under `tests/fixtures/`.
- `data/` and `business/` accept fictitious or anonymized data only.

## CI

`.github/workflows/ci.yml` runs the quality matrix above, then a container job that builds all
image variants and asserts the live contract with curl: `/health`, `/ready`, the four page
titles, `dataset_not_configured` before publication, a six-file Supervisor upload followed by
`dataset_source == "supervisor"` on every agent, 403 on each specialist upload endpoint, 503 on
a Collections query without a dataset, cache-control headers, and the `1001:1001` read-only
container invariants. Changing any of those response shapes means updating this workflow.

`.github/workflows/deploy-k3s.yml` publishes immutable GHCR tags and deploys to K3S.
