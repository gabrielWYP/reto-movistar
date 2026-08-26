"""A completed run publishes its sealed audit object to the configured bucket."""

import gzip
import json
from pathlib import Path

import pytest

import sonia.entrypoints.api as api_module
from sonia.config import Settings
from sonia.entrypoints.api import create_app
from sonia.observability.audit import verify_chain

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "back/tests/fixtures/supervisor"


class StoreStub:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    @property
    def configured(self) -> bool:
        return True

    def put(self, key: str, body: bytes, content_type: str) -> str | None:
        assert content_type == "application/gzip"
        self.objects[key] = body
        return f"https://example.invalid/{key}"


def _answers(repository: object, revision: str) -> dict[str, str]:
    questions = repository.questions(revision)  # type: ignore[attr-defined]
    values = {
        "as_of_date": "2026-08-31",
        "objective": "Identificar fuga de ingresos",
        "scope": "Cartera B2B",
    }
    return {item.question_id: values.get(item.question_id, "10") for item in questions}


def test_a_terminal_run_seals_and_stores_its_model_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = StoreStub()
    monkeypatch.setattr(api_module, "object_store_from_environment", lambda: store)
    settings = Settings(
        "SON-IA", "test", "test", "127.0.0.1", 8080, "INFO", ROOT / "front", tmp_path
    )
    app = create_app(settings)
    runner, coordinator = app.state.run_orchestrator, app.state.dataset_coordinator
    files = {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}
    dataset = coordinator.publish(files, idempotency_key="audit")["dataset_revision"]
    ruleset = runner.intake.create_ruleset(dataset, _answers(runner.intake, dataset))
    run_id = runner.create_run(dataset, ruleset.revision_id, "create").run_id
    runner.start(run_id, "start")

    runner.run(run_id, "audit-run")

    assert len(store.objects) == 1
    key, body = next(iter(store.objects.items()))
    assert key.endswith(f"/{run_id}.jsonl.gz")
    records = [json.loads(line) for line in gzip.decompress(body).splitlines() if line]
    assert records and verify_chain(records)
    assert {record["kind"] for record in records} == {"judge"}
    assert all(record["run_id"] == run_id for record in records)
    verdicts = [record["verdict"] for record in records]
    assert verdicts and all(verdict in {"PASS", "RETRY", "MANUAL_REVIEW"} for verdict in verdicts)


def test_an_unconfigured_bucket_leaves_the_run_untouched(tmp_path: Path) -> None:
    """Auditing is additive: without credentials the run behaves exactly as before."""
    settings = Settings(
        "SON-IA", "test", "test", "127.0.0.1", 8080, "INFO", ROOT / "front", tmp_path
    )
    app = create_app(settings)
    runner, coordinator = app.state.run_orchestrator, app.state.dataset_coordinator
    files = {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}
    dataset = coordinator.publish(files, idempotency_key="audit")["dataset_revision"]
    ruleset = runner.intake.create_ruleset(dataset, _answers(runner.intake, dataset))
    run_id = runner.create_run(dataset, ruleset.revision_id, "create").run_id
    runner.start(run_id, "start")

    completed = runner.run(run_id, "audit-run")

    assert completed.state.endswith(("COMPLETED", "MANUAL_REVIEW"))
    assert runner.audit is not None and runner.audit.enabled is False
