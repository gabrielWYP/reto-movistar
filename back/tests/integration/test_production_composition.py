"""Production composition and durable Supervisor API scenarios."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from sonia.config import Settings
from sonia.entrypoints.api import app, create_app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/supervisor"
RUNS = "/api/supervisor/runs"


def _client(root: Path) -> TestClient:
    settings = Settings(
        "SON-IA", "test", "test", "127.0.0.1", 8080, "INFO", root / "front", storage_root=root
    )
    return TestClient(create_app(settings))


def _files() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        ("files", (path.name, path.read_bytes(), "text/csv")) for path in FIXTURES.glob("*.csv")
    ]


def _publish(client: TestClient, key: str = "publish") -> dict[str, Any]:
    response = client.post(
        "/api/supervisor/datasets", files=_files(), headers={"Idempotency-Key": key}
    )
    assert response.status_code == 201
    return response.json()


def _ruleset(client: TestClient, dataset: str) -> str:
    questions = client.get(f"/api/supervisor/datasets/{dataset}/questions")
    assert questions.status_code == 200
    payload = questions.json()
    assert {item["target"] for item in payload} == {"global", "billing", "collections", "bi"}
    answers = {item["question_id"]: "10" for item in payload}
    answers |= {"as_of_date": "2026-08-31", "objective": "Find leakage", "scope": "B2B"}
    response = client.post(
        "/api/supervisor/rulesets", json={"dataset_revision": dataset, "answers": answers}
    )
    assert response.status_code == 201
    return response.json()["revision_id"]


def test_default_app_composes_durable_intake_run_evidence_and_review(tmp_path: Path) -> None:
    assert TestClient(app).get(f"{RUNS}/missing").status_code == 404
    client = _client(tmp_path)
    dataset = _publish(client)
    assert _publish(client) == dataset
    ruleset = _ruleset(client, dataset["dataset_revision"])
    created = client.post(
        RUNS,
        headers={"Idempotency-Key": "create"},
        json={"dataset_revision": dataset["dataset_revision"], "ruleset_revision": ruleset},
    )
    assert created.status_code == 201
    run_id = created.json()["run_id"]
    assert (
        client.post(f"{RUNS}/{run_id}/start", headers={"Idempotency-Key": "start"}).status_code
        == 202
    )
    assert client.get(f"{RUNS}/{run_id}").json()["state"] == "COMPLETED"

    evidence = client.get(f"{RUNS}/{run_id}/evidence")
    assert evidence.status_code == 200
    steps = evidence.json()["evidence"]
    assert [(item["phase"], item["kind"]) for item in steps] == [
        (phase, kind)
        for phase in ("billing", "collections", "bi")
        for kind in ("specialist", "judge")
    ]
    assert steps[0]["content"]["evidence_refs"] and steps[-1]["content"]["verdict"] == "PASS"
    package = client.get(f"{RUNS}/{run_id}/package").json()
    headers = {"Idempotency-Key": "review", "X-Forwarded-User": "analyst@example.com"}
    decision = client.post(
        f"{RUNS}/{run_id}/review",
        headers=headers,
        json={"package_revision": package["package_revision"], "outcome": "accept"},
    )
    assert decision.status_code == 200
    assert client.get(f"{RUNS}/{run_id}/review").json() == decision.json()
    reopened = _client(tmp_path)
    assert reopened.get(f"{RUNS}/{run_id}").json()["state"] == "COMPLETED"
    assert reopened.get(f"{RUNS}/{run_id}/review").json()["analyst_id"] == "analyst@example.com"


def test_supervisor_compatibility_and_whitespace_are_fail_closed(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.post("/api/supervisor/dataset", files=_files()).status_code == 200
    invalid_upload = client.post(
        "/api/supervisor/datasets", files=_files(), headers={"Idempotency-Key": "   "}
    )
    assert invalid_upload.status_code == 422
    dataset = _publish(client, "durable")["dataset_revision"]
    questions = client.get(f"/api/supervisor/datasets/{dataset}/questions").json()
    answers = {item["question_id"]: "10" for item in questions}
    answers |= {"as_of_date": "2026-08-31", "objective": "   ", "scope": "B2B"}
    invalid = client.post(
        "/api/supervisor/rulesets", json={"dataset_revision": dataset, "answers": answers}
    )
    assert invalid.status_code == 422 and "objective" in invalid.json()["detail"]
    answers["objective"] = "Find leakage"
    ruleset = client.post(
        "/api/supervisor/rulesets", json={"dataset_revision": dataset, "answers": answers}
    ).json()["revision_id"]
    run_id = client.post(
        RUNS,
        headers={"Idempotency-Key": "create"},
        json={"dataset_revision": dataset, "ruleset_revision": ruleset},
    ).json()["run_id"]
    client.post(f"{RUNS}/{run_id}/start", headers={"Idempotency-Key": "start"})
    package = client.get(f"{RUNS}/{run_id}/package").json()["package_revision"]
    url = f"{RUNS}/{run_id}/review"
    trusted = {"Idempotency-Key": "review", "X-Forwarded-User": "analyst-1"}
    accept = {"package_revision": package, "outcome": "accept"}
    cases = (
        (trusted, accept | {"outcome": "reject", "reason": "   "}, 422),
        (trusted, accept | {"annotation": "   "}, 422),
        ({"Idempotency-Key": "review", "X-Forwarded-User": "   "}, accept, 401),
        ({"Idempotency-Key": "   ", "X-Forwarded-User": "analyst-1"}, accept, 422),
    )
    for headers, body, status in cases:
        assert client.post(url, headers=headers, json=body).status_code == status
