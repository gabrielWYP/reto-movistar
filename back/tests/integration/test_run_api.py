from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks
from fastapi.testclient import TestClient

from sonia.application.judge import Judge
from sonia.application.orchestrator import RunOrchestrator
from sonia.application.specialist_adapters import SpecialistAdapter
from sonia.config import Settings
from sonia.domain.orchestration import (
    ExecutionMetadata,
    RunState,
    SpecialistPhase,
    SpecialistResult,
    ValidationCheck,
)
from sonia.entrypoints.api import create_app
from sonia.persistence.backup import StorageHardener
from sonia.persistence.sqlite import SQLiteIntakeRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/supervisor"


class Probe:
    def __init__(self, phase: SpecialistPhase) -> None:
        self.phase = phase

    def __call__(self, at: str) -> dict[str, Any]:
        return {
            "agent": self.phase,
            "status": "RESULT_AVAILABLE",
            "data_quality": {"bounded_at": at},
            "recommended_actions": [{"action": f"review {self.phase}"}],
        }


def _system(root: Path, judge: Judge | None = None) -> tuple[TestClient, str, str, RunOrchestrator]:
    intake = SQLiteIntakeRepository(root)
    files = {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}
    dataset = intake.publish_dataset(files, "upload")
    answers = {item.question_id: "10" for item in intake.questions(dataset.revision_id)}
    answers |= {"as_of_date": "2026-08-31", "objective": "Find leakage", "scope": "B2B"}
    intake.create_ruleset(dataset.revision_id, answers)
    revised = intake.create_ruleset(dataset.revision_id, answers | {"scope": "Enterprise"})
    adapters = {phase: SpecialistAdapter(phase, Probe(phase)) for phase in SpecialistPhase}
    runner = RunOrchestrator(
        root / "db/sonia.sqlite3", intake, adapters, judge or Judge(), owner="api"
    )
    settings = Settings("SON-IA", "test", "test", "127.0.0.1", 8080, "INFO", root / "front")
    app = create_app(settings, run_orchestrator=runner, run_storage=StorageHardener(root))
    return TestClient(app), dataset.revision_id, revised.revision_id, runner


def _create(client: TestClient, dataset: str, ruleset: str, key: str = "create") -> dict[str, Any]:
    response = client.post(
        "/api/supervisor/runs",
        headers={"Idempotency-Key": key},
        json={"dataset_revision": dataset, "ruleset_revision": ruleset},
    )
    assert response.status_code == 201
    return response.json()


def test_run_start_poll_package_and_history_are_idempotent(tmp_path: Path) -> None:
    client, dataset, revised, runner = _system(tmp_path)
    ruleset = runner.intake.get_ruleset(revised)
    assert ruleset is not None
    original = runner.intake.create_ruleset(
        dataset, {item.rule_id: item.answer for item in ruleset.rules} | {"scope": "B2B"}
    ).revision_id
    created = _create(client, dataset, original)
    assert _create(client, dataset, original) == created
    conflict = client.post(
        "/api/supervisor/runs",
        headers={"Idempotency-Key": "create"},
        json={"dataset_revision": dataset, "ruleset_revision": revised},
    )
    assert conflict.status_code == 409

    run_id = created["run_id"]
    started = client.post(
        f"/api/supervisor/runs/{run_id}/start", headers={"Idempotency-Key": "start"}
    )
    resumed = client.post(
        f"/api/supervisor/runs/{run_id}/start", headers={"Idempotency-Key": "start"}
    )
    assert started.status_code == resumed.status_code == 202
    assert resumed.json()["state"] == "COMPLETED"
    assert client.get(f"/api/supervisor/runs/{run_id}").json()["state"] == "COMPLETED"
    package = client.get(f"/api/supervisor/runs/{run_id}/package")
    history = client.get(f"/api/supervisor/runs/{run_id}/history").json()["history"]
    assert package.status_code == 200 and len(package.json()["package_revision"]) == 64
    assert history == "billing billing:judge collections collections:judge bi bi:judge".split()


def test_active_start_directly_schedules_resume_from_current_snapshot(tmp_path: Path) -> None:
    client, dataset, ruleset, runner = _system(tmp_path)
    run = runner.create_run(dataset, ruleset, "create-direct")
    runner.start(run.run_id, "start-direct")
    runner.advance(run.run_id, RunState.BILLING_RUNNING, "billing-direct")
    route = next(
        route
        for included in client.app.routes
        for route in getattr(getattr(included, "original_router", None), "routes", ())
        if route.path == "/api/supervisor/runs/{run_id}/start"
    )
    background = BackgroundTasks()

    resumed = route.endpoint(run.run_id, background, "start-direct")

    assert resumed.state is RunState.BILLING_JUDGING
    assert len(background.tasks) == 1
    completed = runner.run(run.run_id, "background:start-direct")
    assert completed.state is RunState.COMPLETED
    assert runner.history(run.run_id).count("billing") == 1
    client.close()


def test_completed_review_is_append_only_and_digest_idempotent(tmp_path: Path) -> None:
    client, dataset, ruleset, runner = _system(tmp_path)
    run_id = _create(client, dataset, ruleset)["run_id"]
    client.post(f"/api/supervisor/runs/{run_id}/start", headers={"Idempotency-Key": "start"})
    package = client.get(f"/api/supervisor/runs/{run_id}/package").json()
    before = runner.get_run(run_id), runner.history(run_id)
    body = {"package_revision": package["package_revision"], "outcome": "accept"}
    headers = {"Idempotency-Key": "review", "X-Forwarded-User": "analyst@example.com"}
    accepted = client.post(f"/api/supervisor/runs/{run_id}/review", headers=headers, json=body)
    replay = client.post(f"/api/supervisor/runs/{run_id}/review", headers=headers, json=body)
    assert accepted.status_code == replay.status_code == 200
    assert accepted.json() == replay.json()
    assert accepted.json()["identity_header"] == "X-Forwarded-User"
    assert accepted.json()["package_digest"] == package["envelope"]["sha256"]
    assert (runner.get_run(run_id), runner.history(run_id)) == before
    url = f"/api/supervisor/runs/{run_id}/review"
    changed = client.post(url, headers=headers, json=body | {"annotation": "changed"})
    duplicate = client.post(
        url,
        headers=headers | {"Idempotency-Key": "another"},
        json=body,
    )
    assert changed.status_code == duplicate.status_code == 409


def test_manual_package_reject_requires_reason_and_identity(tmp_path: Path) -> None:
    def reject(result: SpecialistResult) -> tuple[tuple[ValidationCheck, ...], ExecutionMetadata]:
        check = ValidationCheck(name="quality", passed=False, detail="unresolved")
        return (check,), ExecutionMetadata(latency_ms=result.attempt, token_count=0)

    client, dataset, ruleset, _ = _system(tmp_path, Judge(reject))
    run_id = _create(client, dataset, ruleset)["run_id"]
    client.post(f"/api/supervisor/runs/{run_id}/start", headers={"Idempotency-Key": "start"})
    package = client.get(f"/api/supervisor/runs/{run_id}/package").json()
    body = {"package_revision": package["package_revision"], "outcome": "reject"}
    url = f"/api/supervisor/runs/{run_id}/review"
    accept = body | {"outcome": "accept"}
    assert client.post(url, headers={"Idempotency-Key": "r"}, json=accept).status_code == 401
    bad_identity = {"Idempotency-Key": "r", "X-Forwarded-User": "bad identity"}
    assert client.post(url, headers=bad_identity, json=accept).status_code == 401
    trusted = {"Idempotency-Key": "r", "X-Forwarded-User": "analyst-7"}
    assert client.post(url, headers=trusted, json=body).status_code == 422
    decided = client.post(url, headers=trusted, json=body | {"reason": "unresolved quality"})
    assert decided.status_code == 200 and decided.json()["outcome"] == "reject"


def test_review_rejects_package_mismatch_and_corruption(tmp_path: Path) -> None:
    client, dataset, ruleset, _ = _system(tmp_path)
    run_id = _create(client, dataset, ruleset)["run_id"]
    client.post(f"/api/supervisor/runs/{run_id}/start", headers={"Idempotency-Key": "start"})
    package = client.get(f"/api/supervisor/runs/{run_id}/package").json()
    headers = {"Idempotency-Key": "review", "X-Forwarded-User": "analyst-7"}
    body = {"package_revision": "0" * 64, "outcome": "accept"}
    url = f"/api/supervisor/runs/{run_id}/review"
    assert client.post(url, headers=headers, json=body).status_code == 409
    package_path = tmp_path / "packages" / f"{run_id}.json"
    package_path.write_text("{}")
    body["package_revision"] = package["package_revision"]
    assert client.post(url, headers=headers, json=body).status_code == 503
