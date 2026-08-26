"""SQLite and immutable-file persistence for Supervisor intake."""

from __future__ import annotations

import csv
import io
import os
import sqlite3
import tempfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

from bi_agent.data import TABLE_FILES
from pydantic import Field

from sonia.domain.orchestration import BusinessRule, ImmutableModel, external_effect_rule_ids

CSV_ENCODINGS = ("utf-8-sig", "utf-8", "latin1", "cp1252")


def decode_csv_text(content: bytes) -> str:
    """Decode one official source, tolerating the cp1252 exports Movistar ships."""
    for encoding in CSV_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo decodificar el CSV. Usa UTF-8, ANSI o Windows-1252.")


def count_csv_rows(content: bytes) -> int:
    """Count data rows, excluding the header."""
    rows = list(csv.reader(io.StringIO(decode_csv_text(content)), delimiter="|"))
    return len(rows) - 1


_QUESTION_DEFS = (
    (
        "as_of_date",
        "global",
        "date",
        None,
        "Fecha de corte",
        "Última fecha considerada. Nada posterior entra al análisis.",
        "",
        "",
    ),
    (
        "objective",
        "global",
        "text",
        None,
        "Objetivo del análisis",
        "Qué buscas detectar en este ciclo.",
        "",
        "",
    ),
    (
        "scope",
        "global",
        "text",
        None,
        "Alcance",
        "Cartera o segmento a revisar.",
        "",
        "",
    ),
    (
        "billing_materiality",
        "billing",
        "number",
        "invoices",
        "Umbral de materialidad",
        "Diferencia mínima en soles para reportar un hallazgo de facturación.",
        "S/",
        "100",
    ),
    (
        "overdue_days",
        "collections",
        "number",
        "payments",
        "Días de vencimiento",
        "A partir de cuántos días de mora se considera deuda exigible.",
        "días",
        "30",
    ),
    (
        "variance_threshold",
        "bi",
        "number",
        "invoices",
        "Variación significativa",
        "Desvío mínimo contra el periodo anterior para marcar el caso.",
        "%",
        "10",
    ),
)


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
    """Typed question traceable to a profile or requirement.

    ``label``, ``help``, ``unit`` and ``default`` exist so the operations centre
    can render business language instead of the raw identifier.
    """

    question_id: str
    target: str
    answer_type: str
    mandatory: bool = True
    evidence: str
    label: str
    help: str
    unit: str = ""
    default: str = ""


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

    def publish_dataset(
        self,
        files: dict[str, bytes],
        idempotency_key: str,
        *,
        row_counts: Mapping[str, int] | None = None,
    ) -> DatasetRevision:
        """Atomically bind a request key to one immutable dataset revision.

        Callers that already parsed the sources during validation pass their row
        counts through ``row_counts`` so publication never re-parses the CSVs.
        """
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
            counts = row_counts or {}
            profiles = tuple(
                DatasetFile(
                    source=name,
                    sha256=file_digest,
                    row_count=counts.get(name) or count_csv_rows(content),
                    path=path,
                )
                for name, content in sorted(files.items())
                for file_digest, path in (self._atomic_write(revision_id, content),)
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

    def latest_dataset(self) -> DatasetRevision | None:
        """Return the newest durable Supervisor publication, if one exists."""
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM datasets").fetchall()
        revisions = tuple(DatasetRevision.model_validate_json(row["payload"]) for row in rows)
        return max(revisions, key=lambda item: item.created_at, default=None)

    def read_dataset_files(self, revision_id: str) -> dict[str, bytes]:
        """Read one immutable revision after containment and checksum validation."""
        revision = self.get_dataset(revision_id)
        if revision is None:
            raise KeyError(revision_id)
        files: dict[str, bytes] = {}
        for item in revision.files:
            path = item.path.resolve()
            if not path.is_relative_to(self._dataset_root) or item.path.is_symlink():
                raise RuntimeError("Dataset path escapes durable storage")
            content = path.read_bytes()
            if sha256(content).hexdigest() != item.sha256:
                raise RuntimeError("Dataset checksum verification failed")
            files[item.source] = content
        return files

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
                label=label,
                help=help_text,
                unit=unit,
                default=default,
            )
            for (
                question_id,
                target,
                answer_type,
                source,
                label,
                help_text,
                unit,
                default,
            ) in _QUESTION_DEFS
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
            f"Unsupported external-effect instruction: {rule_id}"
            for rule_id in external_effect_rule_ids(rules)
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
