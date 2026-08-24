"""Behavioral contract for the autonomous Supervisor browser journey."""

from pathlib import Path

from fastapi.testclient import TestClient

from sonia.config import Settings
from sonia.entrypoints.api import create_app

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "back/tests/fixtures/supervisor"
HTML = (ROOT / "front/index.html").read_text(encoding="utf-8")
JS = (ROOT / "front/assets/app.js").read_text(encoding="utf-8")


def test_supervisor_ui_drives_intake_run_evidence_and_one_final_review() -> None:
    """The browser follows the durable API without intermediate approvals."""
    element_ids = (
        "rule-questions run-progress judge-history evidence-output package-output "
        "review-form review-outcome review-reason review-annotation"
    ).split()
    for element_id in element_ids:
        assert f'id="{element_id}"' in HTML
    routes = (
        "/api/supervisor/datasets /questions /api/supervisor/rulesets "
        "/api/supervisor/runs /start /history /evidence /package /review"
    ).split()
    for route in routes:
        assert route in JS
    assert 'aria-live="polite"' in HTML and 'aria-busy="false"' in HTML
    assert "pollRun" in JS and "lockReview" in JS and "syncReviewReason" in JS
    assert "/api/demo" not in JS and "X-Forwarded-User" not in JS


def test_only_supervisor_has_manual_intake_and_specialists_are_read_only() -> None:
    """Specialist navigation remains available without local upload controls."""
    assert HTML.count('type="file"') == 1
    for path in "Agente BI/FRONT|Agente Cobranzas/FRONT|Agente_Facturacion/FRONT".split("|"):
        frontend = ROOT / path
        assert 'type="file"' not in (frontend / "index.html").read_text(encoding="utf-8")
        assert "new FormData()" not in (frontend / "assets/app.js").read_text(encoding="utf-8")
    assert all(link in HTML for link in ("/agents/billing/", "/agents/collections/", "/bi/"))


def test_ui_request_contract_reaches_terminal_evidence(tmp_path: Path) -> None:
    """The exact browser request contract reaches a durable terminal state."""
    settings = Settings(
        "SON-IA", "test", "test", "127.0.0.1", 8080, "INFO", ROOT / "front", tmp_path
    )
    client = TestClient(create_app(settings))
    files = [
        ("files", (path.name, path.read_bytes(), "text/csv")) for path in FIXTURES.glob("*.csv")
    ]
    dataset = client.post(
        "/api/supervisor/datasets", files=files, headers={"Idempotency-Key": "ui-dataset"}
    ).json()["dataset_revision"]
    questions = client.get(f"/api/supervisor/datasets/{dataset}/questions").json()
    answers = {item["question_id"]: "10" for item in questions}
    answers |= {"as_of_date": "2026-08-31", "objective": "Find leakage", "scope": "B2B"}
    ruleset = client.post(
        "/api/supervisor/rulesets", json={"dataset_revision": dataset, "answers": answers}
    ).json()["revision_id"]
    run = client.post(
        "/api/supervisor/runs",
        headers={"Idempotency-Key": "ui-run"},
        json={"dataset_revision": dataset, "ruleset_revision": ruleset},
    ).json()["run_id"]
    started = client.post(
        f"/api/supervisor/runs/{run}/start", headers={"Idempotency-Key": "ui-start"}
    )
    evidence = client.get(f"/api/supervisor/runs/{run}/evidence").json()["evidence"]
    assert (
        started.status_code == 202
        and client.get(f"/api/supervisor/runs/{run}").json()["state"] == "COMPLETED"
    )
    assert [(item["phase"], item["kind"], item["attempt"]) for item in evidence] == [
        ("billing", "specialist", 1),
        ("billing", "judge", 1),
        ("billing", "specialist", 2),
        ("billing", "judge", 2),
        ("collections", "specialist", 1),
        ("collections", "judge", 1),
        ("bi", "specialist", 1),
        ("bi", "judge", 1),
    ]
    assert all(item["content"] for item in evidence)
