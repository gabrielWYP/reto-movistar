"""Production restart recovery with Supervisor-owned durable datasets."""

from pathlib import Path

from sonia.config import Settings
from sonia.domain.orchestration import RunState
from sonia.entrypoints.api import create_app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/supervisor"


def _settings(root: Path) -> Settings:
    return Settings("SON-IA", "test", "test", "127.0.0.1", 8080, "INFO", root / "front", root)


def test_recreated_app_rehydrates_bound_dataset_and_resumes_without_duplicates(
    tmp_path: Path,
) -> None:
    files = {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}
    first = create_app(_settings(tmp_path))
    published = first.state.dataset_coordinator.publish(files, idempotency_key="upload")
    runner = first.state.run_orchestrator
    dataset = published["dataset_revision"]
    answers = {item.question_id: "10" for item in runner.intake.questions(dataset)}
    answers |= {"as_of_date": "2026-08-31", "objective": "Find leakage", "scope": "B2B"}
    ruleset = runner.intake.create_ruleset(dataset, answers).revision_id
    created = runner.create_run(dataset, ruleset, "create")
    runner.start(created.run_id, "start")
    runner.lease_seconds = -1
    runner.advance(created.run_id, RunState.BILLING_RUNNING, "billing-1")
    assert runner.history(created.run_id) == ("billing",)
    changed = dict(files)
    changed["005_TBL_FACTURAS_B2B.csv"] = changed["005_TBL_FACTURAS_B2B.csv"].replace(
        b"|100|18|118", b"|200|36|236"
    )
    assert (
        first.state.dataset_coordinator.publish(changed, idempotency_key="newer-upload")[
            "dataset_revision"
        ]
        != dataset
    )

    recreated = create_app(_settings(tmp_path))
    recovered = recreated.state.run_orchestrator
    assert recreated.state.dataset_coordinator.status()["dataset_configured"] is True
    assert recovered.start(created.run_id, "start").state is RunState.BILLING_JUDGING
    assert recovered.run(created.run_id, "resume").state is RunState.COMPLETED

    evidence = recovered.evidence(created.run_id)
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
    assert [item["content"].get("verdict") for item in evidence if item["kind"] == "judge"] == [
        "RETRY",
        "PASS",
        "PASS",
        "PASS",
    ]
