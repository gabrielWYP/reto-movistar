"""Durable Supervisor intake integration scenarios."""

from __future__ import annotations

from pathlib import Path

import pytest
from bi_agent.application import BIBackend
from billing_agent.config import Settings as BillingSettings
from billing_agent.datasets import DatasetRegistry
from collections_agent.application import CollectionsBackend

from sonia.application.dataset_supervisor import SupervisorDatasetCoordinator
from sonia.persistence.sqlite import SQLiteIntakeRepository, decode_csv_text

FIXTURES = Path(__file__).resolve().parents[3] / "back/tests/fixtures/supervisor"


def _files() -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in FIXTURES.glob("*.csv")}


def _coordinator(tmp_path: Path) -> tuple[SupervisorDatasetCoordinator, SQLiteIntakeRepository]:
    repo = SQLiteIntakeRepository(tmp_path)
    return (
        SupervisorDatasetCoordinator(
            BIBackend(), CollectionsBackend(), DatasetRegistry(BillingSettings()), repo
        ),
        repo,
    )


def _answers(repository: SQLiteIntakeRepository, revision: str) -> dict[str, str]:
    values = {
        "as_of_date": "2026-08-31",
        "objective": "Identify revenue leakage",
        "scope": "B2B portfolio",
    }
    return {
        question.question_id: values.get(question.question_id, "10")
        for question in repository.questions(revision)
    }


def test_publication_is_immutable_profiled_and_questioned(tmp_path: Path) -> None:
    coordinator, repository = _coordinator(tmp_path)

    result = coordinator.publish(_files(), idempotency_key="upload-1")
    revision = repository.get_dataset(result["dataset_revision"])
    questions = repository.questions(result["dataset_revision"])

    assert revision is not None
    assert len(revision.files) == 6
    assert all(len(item.sha256) == 64 and item.row_count > 0 for item in revision.files)
    assert all(
        item.path.is_file() and item.path.is_relative_to(tmp_path) for item in revision.files
    )
    assert {question.target for question in questions} == {"global", "billing", "collections", "bi"}
    assert all(question.mandatory and question.answer_type for question in questions)
    assert all(
        question.evidence.startswith("profile:") or question.evidence == "requirement"
        for question in questions
    )


def test_invalid_and_conflicting_publications_do_not_mutate_storage(tmp_path: Path) -> None:
    coordinator, repository = _coordinator(tmp_path)
    incomplete = _files()
    incomplete.pop("004_TBL_PAGOS_B2B.csv")
    with pytest.raises(ValueError, match="Faltan"):
        coordinator.publish(incomplete, idempotency_key="upload-missing")
    assert not (tmp_path / "datasets").exists()
    original = _files()
    first = coordinator.publish(original, idempotency_key="upload-1")
    replay = coordinator.publish(original, idempotency_key="upload-1")
    changed = dict(original)
    changed["004_TBL_PAGOS_B2B.csv"] += b"\n"

    with pytest.raises(ValueError, match="idempotency"):
        coordinator.publish(changed, idempotency_key="upload-1")

    assert replay["dataset_revision"] == first["dataset_revision"]
    assert repository.get_dataset(first["dataset_revision"]) is not None


def test_rulesets_require_answers_and_create_immutable_revisions(tmp_path: Path) -> None:
    coordinator, repository = _coordinator(tmp_path)
    revision = coordinator.publish(_files(), idempotency_key="upload-1")["dataset_revision"]

    with pytest.raises(ValueError, match="mandatory"):
        repository.create_ruleset(revision, {"as_of_date": "2026-08-31"})

    answers = _answers(repository, revision)
    first = repository.create_ruleset(revision, answers)
    changed = repository.create_ruleset(revision, answers | {"scope": "Enterprise accounts"})

    assert first.execution_ready is True
    assert first.dataset_revision == revision
    assert first.revision_id != changed.revision_id
    assert SQLiteIntakeRepository(tmp_path).get_ruleset(first.revision_id) == first


@pytest.mark.parametrize("rule", ["Issue invoices automatically", "Delete all invoice records"])
def test_external_effects_are_recorded_not_executable(tmp_path: Path, rule: str) -> None:
    coordinator, repository = _coordinator(tmp_path)
    revision = coordinator.publish(_files(), idempotency_key="upload-1")["dataset_revision"]
    answers = _answers(repository, revision) | {"objective": rule}

    ruleset = repository.create_ruleset(revision, answers)

    assert ruleset.execution_ready is False
    assert ruleset.rejections == ("Unsupported external-effect instruction: objective",)
    assert next(item.answer for item in ruleset.rules if item.rule_id == "objective") == rule


def _cp1252_files() -> dict[str, bytes]:
    """Real Movistar exports ship cp1252 accents inside RAZON_SOCIAL."""
    return {
        name: content.decode("ascii").replace("CLIENT_001", "André_001").encode("cp1252")
        for name, content in _files().items()
    }


def test_publication_accepts_cp1252_encoded_sources(tmp_path: Path) -> None:
    coordinator, repository = _coordinator(tmp_path)

    result = coordinator.publish(_cp1252_files(), idempotency_key="upload-cp1252")

    revision = repository.get_dataset(result["dataset_revision"])
    assert revision is not None
    assert len(revision.files) == 6
    assert all(item.row_count >= 1 for item in revision.files)


def _cp1252_only_files() -> dict[str, bytes]:
    """Bytes 0x80-0x9F are the range where cp1252 and latin1 disagree."""
    return {
        name: content.decode("ascii").replace("CLIENT_001", "GRUPO—001").encode("cp1252")
        for name, content in _files().items()
    }


def test_publication_preserves_cp1252_only_characters(tmp_path: Path) -> None:
    """A permissive fallback used to store “ ” — € as C1 controls without failing."""
    coordinator, repository = _coordinator(tmp_path)

    result = coordinator.publish(_cp1252_only_files(), idempotency_key="upload-cp1252-only")

    revision = repository.get_dataset(result["dataset_revision"])
    assert revision is not None
    stored = [decode_csv_text(item.path.read_bytes()) for item in revision.files]
    assert any("GRUPO—001" in text for text in stored)
    assert not any(0x80 <= ord(character) <= 0x9F for text in stored for character in text)


def test_status_exposes_revision_after_restart(tmp_path: Path) -> None:
    """A restarted pod must advertise its rehydrated revision without a re-upload."""
    coordinator, _ = _coordinator(tmp_path)
    published = coordinator.publish(_files(), idempotency_key="upload-1")

    restarted, _ = _coordinator(tmp_path)
    restarted.rehydrate_latest()
    status = restarted.status()

    assert status["dataset_configured"] is True
    assert status["dataset_revision"] == published["dataset_revision"]


def test_questions_carry_business_language_for_analysts(tmp_path: Path) -> None:
    """A non-technical analyst answers these, so raw ids are not an interface."""
    coordinator, repository = _coordinator(tmp_path)
    result = coordinator.publish(_files(), idempotency_key="upload-labels")

    questions = repository.questions(result["dataset_revision"])
    by_id = {question.question_id: question for question in questions}

    assert all(question.label and question.help for question in questions)
    assert by_id["as_of_date"].label == "Fecha de corte"
    assert by_id["billing_materiality"].unit == "S/"
    assert by_id["variance_threshold"].unit == "%"
    assert by_id["overdue_days"].unit == "días"
    assert by_id["overdue_days"].default == "30"
