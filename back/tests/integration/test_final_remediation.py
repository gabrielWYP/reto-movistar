"""Direct runtime coverage for durable annotations and final review idempotency."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException

from sonia.application.judge import Judge
from sonia.application.orchestrator import RunOrchestrator
from sonia.application.specialist_adapters import SpecialistAdapter
from sonia.config import Settings
from sonia.domain.orchestration import RunState, SpecialistPhase
from sonia.entrypoints.api import create_app
from sonia.entrypoints.run_api import EvidenceAnnotationRequest, ReviewRequest
from sonia.persistence.backup import StorageHardener
from sonia.persistence.sqlite import SQLiteIntakeRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/supervisor"


class Probe:
    def __init__(self, phase: SpecialistPhase) -> None:
        self.phase, self.calls = phase, 0

    def __call__(self, at: str) -> dict[str, Any]:
        self.calls += 1
        return {"agent": self.phase, "status": "RESULT_AVAILABLE", "data_quality": {"at": at}}


def _system(
    root: Path, *, complete: bool = True
) -> tuple[FastAPI, RunOrchestrator, StorageHardener, dict[SpecialistPhase, Probe], str]:
    intake = SQLiteIntakeRepository(root)
    files = {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}
    dataset = intake.publish_dataset(files, "upload")
    answers = {question.question_id: "10" for question in intake.questions(dataset.revision_id)}
    answers |= {"as_of_date": "2026-08-31", "objective": "Find leakage", "scope": "B2B"}
    ruleset = intake.create_ruleset(dataset.revision_id, answers)
    probes = {phase: Probe(phase) for phase in SpecialistPhase}
    adapters = {phase: SpecialistAdapter(phase, probes[phase]) for phase in SpecialistPhase}
    runner = RunOrchestrator(root / "db/sonia.sqlite3", intake, adapters, Judge(), owner="direct")
    storage = StorageHardener(root)
    settings = Settings("SON-IA", "test", "test", "127.0.0.1", 8080, "INFO", root / "front")
    app = create_app(settings, run_orchestrator=runner, run_storage=storage)
    run = runner.create_run(dataset.revision_id, ruleset.revision_id, "create")
    if complete:
        assert runner.run(run.run_id, "run").state is RunState.COMPLETED
    return app, runner, storage, probes, run.run_id


def _endpoint(app: FastAPI, path: str, method: str) -> Callable[..., object]:
    return next(
        route.endpoint
        for included in app.routes
        for route in getattr(getattr(included, "original_router", None), "routes", ())
        if route.path == path and method in route.methods
    )


def test_intermediate_annotation_is_durable_separate_and_run_neutral(tmp_path: Path) -> None:
    app, runner, storage, _, run_id = _system(tmp_path, complete=False)
    runner.start(run_id, "start")
    runner.advance(run_id, RunState.BILLING_RUNNING, "billing")
    assert runner.get_run(run_id).state is RunState.BILLING_JUDGING
    before = runner.get_run(run_id), runner.history(run_id), runner.evidence(run_id)
    post = _endpoint(app, "/api/supervisor/runs/{run_id}/evidence/{sequence}/annotations", "POST")
    get = _endpoint(app, "/api/supervisor/runs/{run_id}/evidence/{sequence}/annotations", "GET")

    annotation = post(
        run_id, 1, EvidenceAnnotationRequest(annotation="Verify billing variance"), "a1", "gabo"
    )
    replay = post(
        run_id, 1, EvidenceAnnotationRequest(annotation="Verify billing variance"), "a1", "gabo"
    )
    assert annotation == replay and get(run_id, 1) == (annotation,)
    assert (runner.get_run(run_id), runner.history(run_id), runner.evidence(run_id)) == before
    reopened = create_app(
        Settings("SON-IA", "test", "test", "127.0.0.1", 8080, "INFO", tmp_path / "front"),
        run_orchestrator=RunOrchestrator(
            runner.database, runner.intake, runner.adapters, Judge(), owner="reopened"
        ),
        run_storage=storage,
    )
    assert _endpoint(
        reopened, "/api/supervisor/runs/{run_id}/evidence/{sequence}/annotations", "GET"
    )(run_id, 1) == (annotation,)
    with pytest.raises(HTTPException, match="identity"):
        post(run_id, 1, EvidenceAnnotationRequest(annotation="No identity"), "a2", None)
    with pytest.raises(HTTPException, match="evidence"):
        get(run_id, 99)
    with pytest.raises(HTTPException, match="Conflicting annotation"):
        post(run_id, 1, EvidenceAnnotationRequest(annotation="Changed"), "a1", "gabo")
    assert runner.run(run_id, "resume").state is RunState.COMPLETED
    assert runner.history(run_id).count("billing") == 1


def test_direct_review_reject_replay_and_conflict_never_rerun(tmp_path: Path) -> None:
    app, runner, storage, probes, run_id = _system(tmp_path)
    before = runner.get_run(run_id), runner.history(run_id), runner.evidence(run_id)
    package = storage.assemble_package(run_id)
    request = ReviewRequest(
        package_revision=package.sha256, outcome="reject", reason="Needs analyst correction"
    )
    review = _endpoint(app, "/api/supervisor/runs/{run_id}/review", "POST")

    rejected = review(run_id, request, "review-1", "gabo")
    assert review(run_id, request, "review-1", "gabo") == rejected
    with pytest.raises(HTTPException, match="Conflicting review"):
        review(run_id, request.model_copy(update={"annotation": "changed"}), "review-1", "gabo")
    assert (runner.get_run(run_id), runner.history(run_id), runner.evidence(run_id)) == before
    assert [probe.calls for probe in probes.values()] == [1, 1, 1]
