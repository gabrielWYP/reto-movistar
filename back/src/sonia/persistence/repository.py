"""Persistence ports for durable, optimistic orchestration storage."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sonia.domain.orchestration import JudgeDecision, RevenueAnalysisRun, SpecialistResult


@runtime_checkable
class OrchestrationRepository(Protocol):
    """State repository implemented by the later SQLite adapter."""

    def get_run(self, run_id: str) -> RevenueAnalysisRun | None:
        """Return an immutable run snapshot, if present."""
        ...

    def create_run(self, run: RevenueAnalysisRun) -> RevenueAnalysisRun:
        """Persist a new revision-bound run or reject a duplicate identifier."""
        ...

    def save_run(
        self,
        run: RevenueAnalysisRun,
        *,
        expected_version: int,
    ) -> RevenueAnalysisRun:
        """Atomically persist a transition when the expected version matches."""
        ...

    def append_specialist_result(self, run_id: str, result: SpecialistResult) -> None:
        """Append normalized specialist evidence for one immutable attempt."""
        ...

    def append_judge_decision(self, run_id: str, decision: JudgeDecision) -> None:
        """Append a verdict without replacing prior Judge evidence."""
        ...
