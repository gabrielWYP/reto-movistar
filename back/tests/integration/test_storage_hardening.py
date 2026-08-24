"""Storage readiness, quarantine, and backup/restore scenarios."""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from sonia.application.judge import Judge
from sonia.application.orchestrator import RunOrchestrator
from sonia.application.specialist_adapters import SpecialistAdapter
from sonia.domain.orchestration import (
    RunState,
    SpecialistPhase,
)
from sonia.persistence.backup import StorageHardener
from sonia.persistence.sqlite import SQLiteIntakeRepository

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/supervisor"


class Probe:
    def __init__(self, phase: SpecialistPhase) -> None:
        self.phase, self.calls = phase, 0

    def __call__(self, at: str) -> dict[str, Any]:
        self.calls += 1
        return {"agent": self.phase, "status": "RESULT_AVAILABLE", "data_quality": {"at": at}}


def _intake(root: Path) -> tuple[SQLiteIntakeRepository, str, str]:
    repository = SQLiteIntakeRepository(root)
    files = {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}
    dataset = repository.publish_dataset(files, "upload")
    answers = {item.question_id: "10" for item in repository.questions(dataset.revision_id)}
    answers |= {"as_of_date": "2026-08-31", "objective": "Find leakage", "scope": "B2B"}
    ruleset = repository.create_ruleset(dataset.revision_id, answers)
    return repository, dataset.revision_id, ruleset.revision_id


def _runner(
    root: Path, judge: Judge | None = None
) -> tuple[RunOrchestrator, dict[SpecialistPhase, Probe], str]:
    intake, dataset, ruleset = _intake(root)
    probes = {phase: Probe(phase) for phase in SpecialistPhase}
    adapters = {phase: SpecialistAdapter(phase, probes[phase]) for phase in SpecialistPhase}
    hardener = StorageHardener(root)
    runner = RunOrchestrator(
        root / "db/sonia.sqlite3",
        intake,
        adapters,
        judge or Judge(),
        owner="worker",
        storage_guard=hardener.require_ready,
    )
    run = runner.create_run(dataset, ruleset, "create")
    return runner, probes, run.run_id


def test_consistent_backup_manifest_and_restore_drill(tmp_path: Path) -> None:
    live, backup, restored = tmp_path / "live", tmp_path / "backup", tmp_path / "restored"
    _, dataset, _ = _intake(live)
    hardener = StorageHardener(live)

    manifest = hardener.backup(backup)
    recovered = hardener.restore(backup, restored)
    revision = SQLiteIntakeRepository(restored).get_dataset(dataset)

    assert manifest.path.is_file() and len(manifest.sha256) == 64
    assert recovered.verify().ready is True and revision is not None
    assert all(item.path.is_relative_to(restored) for item in revision.files)
    document = json.loads(manifest.path.read_text())
    document["sha256"] = "0" * 64
    manifest.path.write_text(json.dumps(document))
    with pytest.raises(RuntimeError, match="manifest"):
        hardener.restore(backup, tmp_path / "rejected")


def test_backup_and_restore_reject_live_storage_destinations(tmp_path: Path) -> None:
    live, backup = tmp_path / "live", tmp_path / "backup"
    _intake(live)
    hardener = StorageHardener(live)
    with pytest.raises(ValueError, match="live storage"):
        hardener.backup(live / "backup")
    hardener.backup(backup)
    with pytest.raises(ValueError, match="live storage"):
        hardener.restore(backup, live / "restore")


@pytest.mark.parametrize("failure", ["missing", "corrupt", "escape"])
def test_corrupt_reference_freezes_readiness_and_prevents_advance(
    tmp_path: Path, failure: str
) -> None:
    runner, probes, run_id = _runner(tmp_path)
    revision = runner.intake.get_dataset(runner.get_run(run_id).dataset_revision)
    assert revision is not None
    referenced = revision.files[0]
    if failure == "missing":
        referenced.path.unlink()
    elif failure == "corrupt":
        referenced.path.write_bytes(b"tampered")
    else:
        escaped_file = referenced.model_copy(update={"path": tmp_path.parent / "escape.csv"})
        escaped = revision.model_copy(update={"files": (escaped_file,) + revision.files[1:]})
        with sqlite3.connect(runner.database) as connection:
            connection.execute(
                "UPDATE datasets SET payload = ? WHERE revision_id = ?",
                (escaped.model_dump_json(), revision.revision_id),
            )

    with pytest.raises(RuntimeError, match="readiness"):
        runner.start(run_id, "start")
    assert StorageHardener(tmp_path).verify().ready is False
    assert runner.get_run(run_id).state is RunState.CREATED
    assert probes[SpecialistPhase.BILLING].calls == 0


def test_orphans_are_atomically_quarantined_with_audit_metadata(tmp_path: Path) -> None:
    repository, dataset, _ = _intake(tmp_path)
    orphan = tmp_path / "datasets/orphan.csv"
    orphan.write_bytes(b"orphan")
    referenced = repository.get_dataset(dataset).files[0]  # type: ignore[union-attr]
    alias = tmp_path / "datasets/alias.csv"
    alias.symlink_to(referenced.path)

    report = StorageHardener(tmp_path).verify()

    assert report.ready is True and len(report.quarantined) == 2
    assert not orphan.exists() and not alias.exists()
    assert all(
        path.is_file() and path.with_suffix(".audit.json").is_file() for path in report.quarantined
    )
    assert all(item.path.is_file() for item in repository.get_dataset(dataset).files)  # type: ignore[union-attr]
    assert (tmp_path / "db/sonia.sqlite3").is_file()
