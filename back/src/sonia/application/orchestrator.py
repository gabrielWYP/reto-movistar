"""Durable single-owner runner for the fixed revenue-analysis workflow."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Callable
from datetime import date
from hashlib import sha256
from pathlib import Path

from sonia.application.judge import Judge
from sonia.application.specialist_adapters import SpecialistAdapter
from sonia.domain.orchestration import (
    ExecutionPlan,
    JudgeDecision,
    JudgeVerdict,
    RevenueAnalysisRun,
    RunState,
    SpecialistPhase,
    SpecialistResult,
)
from sonia.persistence.backup import Artifact, PackageLineageError, StorageHardener
from sonia.persistence.sqlite import SQLiteIntakeRepository

_LOG = logging.getLogger(__name__)
_AFTER_PASS = {
    RunState.BILLING_JUDGING: RunState.COLLECTIONS_RUNNING,
    RunState.COLLECTIONS_JUDGING: RunState.BI_RUNNING,
    RunState.BI_JUDGING: RunState.COMPLETED,
}
_COMMAND = "INSERT INTO run_commands VALUES (?, ?, ?)"
_UPDATE = "UPDATE runs SET payload = ? WHERE run_id = ?"
_STEP = "INSERT INTO run_steps(run_id, kind, phase, attempt, payload) VALUES (?, ?, ?, ?, ?)"
_RESULTS = "SELECT payload FROM run_steps WHERE run_id = ? AND kind = 'specialist' ORDER BY seq"
_LEASE = "SELECT lease_owner, lease_expires FROM runs WHERE run_id = ?"
_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY,payload TEXT NOT NULL,"
    "lease_owner TEXT,lease_expires REAL NOT NULL DEFAULT 0);"
    "CREATE TABLE IF NOT EXISTS run_commands(key TEXT PRIMARY KEY,digest TEXT NOT NULL,"
    "payload TEXT NOT NULL);CREATE TABLE IF NOT EXISTS run_steps("
    "seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL,kind TEXT NOT NULL,"
    "phase TEXT NOT NULL,attempt INTEGER NOT NULL,payload TEXT NOT NULL,"
    "UNIQUE(run_id,kind,phase,attempt));"
)


class RunOrchestrator:
    """Persist digest-bound commands and advance one leased run at a time."""

    def __init__(
        self,
        database: Path,
        intake: SQLiteIntakeRepository,
        adapters: dict[SpecialistPhase, SpecialistAdapter],
        judge: Judge,
        *,
        owner: str,
        lease_seconds: float = 30.0,
        storage_guard: Callable[[], None] | None = None,
        auto_package: bool = True,
    ) -> None:
        self.database, self.intake = database.resolve(), intake
        self.adapters, self.judge = adapters, judge
        self.owner, self.lease_seconds = owner, lease_seconds
        self.storage_guard = storage_guard
        self.package_storage = (
            StorageHardener(self.database.parent.parent) if auto_package else None
        )
        if not self.database.is_file():
            raise RuntimeError("Durable run storage unavailable")
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        if not self.database.is_file():
            raise RuntimeError("Durable run storage unavailable")
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _digest(*values: str) -> str:
        return sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _load(connection: sqlite3.Connection, run_id: str) -> RevenueAnalysisRun:
        row = connection.execute("SELECT payload FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RevenueAnalysisRun.model_validate_json(row["payload"])

    @staticmethod
    def _replay(connection: sqlite3.Connection, key: str, digest: str) -> RevenueAnalysisRun | None:
        row = connection.execute(
            "SELECT digest, payload FROM run_commands WHERE key = ?", (key,)
        ).fetchone()
        if row and row["digest"] != digest:
            raise ValueError("Conflicting idempotency key content")
        return RevenueAnalysisRun.model_validate_json(row["payload"]) if row else None

    def get_run(self, run_id: str) -> RevenueAnalysisRun:
        """Return only the last committed durable run snapshot."""
        with self._connect() as connection:
            return self._load(connection, run_id)

    def _guard_storage(self) -> None:
        if self.storage_guard:
            self.storage_guard()

    def create_run(self, dataset: str, ruleset: str, key: str) -> RevenueAnalysisRun:
        """Create a stable run only for compatible execution-ready revisions."""
        digest = self._digest("create", dataset, ruleset)
        with self._connect() as connection:
            replay = self._replay(connection, key, digest)
            if replay:
                return replay
        source, rules = self.intake.get_dataset(dataset), self.intake.get_ruleset(ruleset)
        if source is None or rules is None or rules.dataset_revision != dataset:
            raise ValueError("Dataset and ruleset revisions are not compatible")
        if not rules.execution_ready:
            raise ValueError("Ruleset is not execution-ready")
        run = RevenueAnalysisRun(
            run_id=f"run_{self._digest(dataset, ruleset)[:20]}",
            dataset_revision=dataset,
            ruleset_revision=ruleset,
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._replay(connection, key, digest)
            if replay:
                return replay
            connection.execute(
                "INSERT OR IGNORE INTO runs VALUES (?, ?, NULL, 0)",
                (run.run_id, run.model_dump_json()),
            )
            committed = self._load(connection, run.run_id)
            connection.execute(_COMMAND, (key, digest, committed.model_dump_json()))
        return committed

    def start(self, run_id: str, key: str) -> RevenueAnalysisRun:
        """Idempotently make Billing the only eligible first specialist."""
        self._guard_storage()
        digest = self._digest("start", run_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._replay(connection, key, digest)
            if replay:
                return replay
            run = self._load(connection, run_id)
            started = run.transition_to(RunState.BILLING_RUNNING)
            connection.execute(_UPDATE, (started.model_dump_json(), run_id))
            connection.execute(_COMMAND, (key, digest, started.model_dump_json()))
        return started

    def _results(self, run_id: str) -> tuple[SpecialistResult, ...]:
        with self._connect() as connection:
            rows = connection.execute(_RESULTS, (run_id,)).fetchall()
        return tuple(SpecialistResult.model_validate_json(row["payload"]) for row in rows)

    def _plan(self, run: RevenueAnalysisRun, phase: SpecialistPhase) -> ExecutionPlan:
        ruleset = self.intake.get_ruleset(run.ruleset_revision)
        if ruleset is None:
            raise RuntimeError("Bound ruleset storage unavailable")
        values = {rule.rule_id: rule.answer for rule in ruleset.rules}
        upstream = tuple(
            ref for result in self._results(run.run_id) for ref in result.evidence_refs
        )
        return ExecutionPlan(
            run_id=run.run_id,
            dataset_revision=run.dataset_revision,
            ruleset_revision=run.ruleset_revision,
            as_of_date=date.fromisoformat(values["as_of_date"]),
            phase=phase,
            global_rules=ruleset.rules,
            upstream_evidence=upstream,
        )

    def advance(self, run_id: str, expected: RunState, key: str) -> RevenueAnalysisRun:
        """Execute exactly one leased specialist or Judge step and commit atomically."""
        self._guard_storage()
        digest = self._digest("advance", run_id, expected)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._replay(connection, key, digest)
            if replay:
                return replay
            run = self._load(connection, run_id)
            if run.state is not expected:
                raise ValueError(f"Expected state {expected}; found {run.state}")
            lease = connection.execute(_LEASE, (run_id,)).fetchone()
            if (
                lease["lease_owner"] not in (None, self.owner)
                and lease["lease_expires"] > time.time()
            ):
                raise RuntimeError(f"Run is leased by {lease['lease_owner']}")
            recovery = lease["lease_owner"] not in (None, self.owner)
            connection.execute(
                "UPDATE runs SET lease_owner = ?, lease_expires = ? WHERE run_id = ?",
                (self.owner, time.time() + self.lease_seconds, run_id),
            )
        if expected.endswith("_RUNNING"):
            phase = SpecialistPhase(expected.removesuffix("_RUNNING").lower())
            results = self._results(run_id)
            attempt = sum(item.phase is phase for item in results) + 1
            step: SpecialistResult | JudgeDecision = self.adapters[phase].execute(
                self._plan(run, phase), attempt=attempt
            )
            state = RunState[f"{phase.name}_JUDGING"]
        else:
            if not expected.endswith("_JUDGING"):
                raise ValueError(f"State {expected} cannot advance")
            phase = SpecialistPhase(expected.removesuffix("_JUDGING").lower())
            results = self._results(run_id)
            current_result = results[-1]
            previous = next((item for item in reversed(results[:-1]) if item.phase is phase), None)
            step = self.judge.evaluate(current_result, previous=previous)
            state = (
                _AFTER_PASS[expected]
                if step.verdict is JudgeVerdict.PASS
                else RunState[f"{phase.name}_RUNNING"]
            )
            if step.verdict is JudgeVerdict.MANUAL_REVIEW:
                state = RunState.MANUAL_REVIEW
        advanced = run.model_copy(update={"state": state, "version": run.version + 1})
        kind = "specialist" if isinstance(step, SpecialistResult) else "judge"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._load(connection, run_id)
            lease = connection.execute(
                "SELECT lease_owner FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if current != run or lease["lease_owner"] != self.owner:
                raise RuntimeError("Run ownership or committed version changed")
            connection.execute(_STEP, (run_id, kind, phase, step.attempt, step.model_dump_json()))
            connection.execute(_UPDATE, (advanced.model_dump_json(), run_id))
            connection.execute(_COMMAND, (key, digest, advanced.model_dump_json()))
        _LOG.info(
            "run_step_committed",
            extra={
                "run_id": run_id,
                "dataset_revision": run.dataset_revision,
                "phase": phase,
                "attempt": step.attempt,
                "verdict": getattr(step, "verdict", None),
                "lease": self.owner,
                "latency_ms": step.metadata.latency_ms,
                "tokens": step.metadata.token_count,
                "recovery": recovery,
            },
        )
        if advanced.state in (RunState.COMPLETED, RunState.MANUAL_REVIEW):
            if self.package_storage:
                self.assemble_review_package(run_id, self.package_storage)
        return advanced

    def run(self, run_id: str, key_prefix: str, *, max_steps: int = 13) -> RevenueAnalysisRun:
        """Provide a bounded callable suitable for a supervised background task."""
        for _ in range(max_steps):
            current = self.get_run(run_id)
            if current.state in (RunState.COMPLETED, RunState.MANUAL_REVIEW):
                if self.package_storage and not current.manual_reason:
                    self.assemble_review_package(run_id, self.package_storage)
                return current
            if current.state is RunState.CREATED:
                self.start(run_id, f"{key_prefix}:{current.version}")
            else:
                self.advance(run_id, current.state, f"{key_prefix}:{current.version}")
        raise RuntimeError("Bounded runner step limit reached")

    def history(self, run_id: str) -> tuple[str, ...]:
        """Return durable specialist/Judge order for audit and recovery."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT phase, kind FROM run_steps WHERE run_id = ? ORDER BY seq", (run_id,)
            ).fetchall()
        return tuple(row["phase"] + (":judge" if row["kind"] == "judge" else "") for row in rows)

    def evidence(self, run_id: str) -> tuple[dict[str, object], ...]:
        """Return immutable committed specialist and Judge contents in order."""
        self.get_run(run_id)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT seq,kind,phase,attempt,payload FROM run_steps "
                "WHERE run_id = ? ORDER BY seq",
                (run_id,),
            ).fetchall()
        return tuple(
            {
                "sequence": row["seq"],
                "kind": row["kind"],
                "phase": row["phase"],
                "attempt": row["attempt"],
                "content": json.loads(row["payload"]),
            }
            for row in rows
        )

    def assemble_review_package(self, run_id: str, storage: StorageHardener) -> Artifact:
        """Assemble terminal evidence or durably escalate incomplete completed lineage."""
        try:
            return storage.assemble_package(run_id)
        except PackageLineageError as error:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                run = self._load(connection, run_id)
                if run.state is RunState.COMPLETED or not run.manual_reason:
                    escalated = run.model_copy(
                        update={
                            "state": RunState.MANUAL_REVIEW,
                            "version": run.version + 1,
                            "manual_reason": run.manual_reason or error.missing,
                        }
                    )
                    connection.execute(_UPDATE, (escalated.model_dump_json(), run_id))
            _LOG.warning(
                "run_package_lineage_failed",
                extra={"run_id": run_id, "missing_lineage": error.missing},
            )
            raise
