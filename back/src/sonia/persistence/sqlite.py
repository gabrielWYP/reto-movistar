"""SQLite and immutable-file persistence for Supervisor intake."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
import tempfile
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

from bi_agent.data import TABLE_FILES
from pydantic import Field

from sonia.domain.orchestration import BusinessRule, ImmutableModel

_QUESTION_DEFS = (
    ("as_of_date", "global", "date", None),
    ("objective", "global", "text", None),
    ("scope", "global", "text", None),
    ("billing_materiality", "billing", "number", "invoices"),
    ("overdue_days", "collections", "number", "payments"),
    ("variance_threshold", "bi", "number", "invoices"),
)
_FORBIDDEN_EFFECTS = (
    "issue invoice|apply payment|contact customer|delete|"
    "emitir factura|aplicar pago|contactar cliente|eliminar"
).split("|")


class DatasetFile(ImmutableModel):
    """Integrity and profile evidence for one immutable source."""

    source: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    row_count: int = Field(ge=1)
    path: Path


class DatasetRevision(ImmutableModel):
    """Published six-source dataset revision."""

    revision_id: str
    created_at: datetime
    files: tuple[DatasetFile, ...]


class RuleQuestion(ImmutableModel):
    """Typed question traceable to a profile or requirement."""

    question_id: str
    target: str
    answer_type: str
    mandatory: bool = True
    evidence: str


class RulesetRevision(ImmutableModel):
    """Immutable normalized rule answers bound to one dataset."""

    revision_id: str
    dataset_revision: str
    rules: tuple[BusinessRule, ...]
    execution_ready: bool
    rejections: tuple[str, ...] = ()


class SQLiteIntakeRepository:
    """Persist intake transactions and immutable source bytes on one root."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._dataset_root = self._root / "datasets"
        self._database = self._root / "db" / "sonia.sqlite3"
        self._database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS datasets
                    (revision_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS publication_keys
                    (key TEXT PRIMARY KEY, digest TEXT NOT NULL, revision_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rulesets
                    (revision_id TEXT PRIMARY KEY, dataset_revision TEXT NOT NULL,
                     payload TEXT NOT NULL);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _digest(files: dict[str, bytes]) -> str:
        digest = sha256()
        for name, content in sorted(files.items()):
            digest.update(name.encode() + b"\0" + sha256(content).digest())
        return digest.hexdigest()

    def _atomic_write(self, revision: str, content: bytes) -> tuple[str, Path]:
        content_digest = sha256(content).hexdigest()
        directory = (self._dataset_root / revision).resolve()
        if not directory.is_relative_to(self._root):
            raise ValueError("Dataset path escapes the configured storage root")
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{content_digest}.csv"
        if target.exists():
            return content_digest, target
        descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".upload-")
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            directory_descriptor = os.open(directory, os.O_DIRECTORY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return content_digest, target

    @staticmethod
    def _profile(source: str, digest: str, path: Path, content: bytes) -> DatasetFile:
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig")), delimiter="|"))
        return DatasetFile(
            source=source,
            sha256=digest,
            row_count=len(rows) - 1,
            path=path,
        )

    def publish_dataset(self, files: dict[str, bytes], idempotency_key: str) -> DatasetRevision:
        """Atomically bind a request key to one immutable dataset revision."""
        if set(files) != set(TABLE_FILES.values()):
            raise ValueError("A dataset revision requires all six official sources")
        digest = self._digest(files)
        revision_id = f"ds_{digest[:20]}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = connection.execute(
                "SELECT digest, revision_id FROM publication_keys WHERE key = ?",
                (idempotency_key,),
            ).fetchone()
            if replay and replay["digest"] != digest:
                raise ValueError("Conflicting idempotency key content")
            if replay:
                persisted = self.get_dataset(replay["revision_id"])
                if persisted is None:
                    raise RuntimeError("Idempotency record references a missing dataset")
                return persisted
            profiles = tuple(
                self._profile(name, *self._atomic_write(revision_id, content), content)
                for name, content in sorted(files.items())
            )
            revision = DatasetRevision(
                revision_id=revision_id, created_at=datetime.now(UTC), files=profiles
            )
            connection.execute(
                "INSERT OR IGNORE INTO datasets VALUES (?, ?)",
                (revision_id, revision.model_dump_json()),
            )
            connection.execute(
                "INSERT INTO publication_keys VALUES (?, ?, ?)",
                (idempotency_key, digest, revision_id),
            )
        return revision

    def get_dataset(self, revision_id: str) -> DatasetRevision | None:
        """Load an immutable dataset snapshot."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM datasets WHERE revision_id = ?", (revision_id,)
            ).fetchone()
        return DatasetRevision.model_validate_json(row["payload"]) if row else None

    def questions(self, revision_id: str) -> tuple[RuleQuestion, ...]:
        """Derive bounded typed questions without exposing raw source rows."""
        dataset = self.get_dataset(revision_id)
        if dataset is None:
            raise KeyError(revision_id)
        evidence = {
            item.source: f"profile:{item.source}:rows={item.row_count}" for item in dataset.files
        }
        return tuple(
            RuleQuestion(
                question_id=question_id,
                target=target,
                answer_type=answer_type,
                evidence=evidence[TABLE_FILES[source]] if source else "requirement",
            )
            for question_id, target, answer_type, source in _QUESTION_DEFS
        )

    def create_ruleset(self, dataset_revision: str, answers: dict[str, str]) -> RulesetRevision:
        """Validate answers and persist an immutable, revision-bound ruleset."""
        questions = self.questions(dataset_revision)
        missing = [
            item.question_id for item in questions if not answers.get(item.question_id, "").strip()
        ]
        if missing:
            raise ValueError("Missing mandatory answers: " + ", ".join(missing))
        for question in questions:
            answer = answers[question.question_id].strip()
            try:
                date.fromisoformat(answer) if question.answer_type == "date" else None
                float(answer) if question.answer_type == "number" else None
            except ValueError as error:
                raise ValueError(
                    f"Invalid {question.answer_type} answer: {question.question_id}"
                ) from error
        rules = tuple(
            BusinessRule(rule_id=item.question_id, answer=answers[item.question_id].strip())
            for item in questions
        )
        rejected = tuple(
            f"Unsupported external-effect instruction: {rule.rule_id}"
            for rule in rules
            if any(term in rule.answer.lower() for term in _FORBIDDEN_EFFECTS)
        )
        serialized = (
            dataset_revision + "|" + "|".join(f"{rule.rule_id}={rule.answer}" for rule in rules)
        )
        digest = sha256(serialized.encode()).hexdigest()
        ruleset = RulesetRevision(
            revision_id=f"rs_{digest[:20]}",
            dataset_revision=dataset_revision,
            rules=rules,
            execution_ready=not rejected,
            rejections=rejected,
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO rulesets VALUES (?, ?, ?)",
                (ruleset.revision_id, dataset_revision, ruleset.model_dump_json()),
            )
        return ruleset

    def get_ruleset(self, revision_id: str) -> RulesetRevision | None:
        """Load an immutable ruleset snapshot."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM rulesets WHERE revision_id = ?", (revision_id,)
            ).fetchone()
        return RulesetRevision.model_validate_json(row["payload"]) if row else None
