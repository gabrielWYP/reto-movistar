"""Operator-only durable checkpoint requests for controlled pod restarts."""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from sonia.domain.orchestration import RevenueAnalysisRun, RunState

_LOG = logging.getLogger(__name__)
_SCHEMA = "sonia.operator-checkpoint/v1"
_FIELDS = {"schema", "request_id", "run_id", "target_state", "sha256"}
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_ORDER = {
    state: index
    for index, state in enumerate(
        (
            RunState.CREATED,
            RunState.BILLING_RUNNING,
            RunState.BILLING_JUDGING,
            RunState.COLLECTIONS_RUNNING,
            RunState.COLLECTIONS_JUDGING,
            RunState.BI_RUNNING,
            RunState.BI_JUDGING,
            RunState.COMPLETED,
        )
    )
}
_LEGAL_TARGETS = set(_ORDER) - {RunState.CREATED, RunState.COMPLETED}


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


class OperatorCheckpointStore:
    """Validate and atomically consume one checksummed request per run."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.requests = self.root / "checkpoints"
        self.consumed = self.requests / "consumed"

    def _request_path(self, run_id: str) -> Path:
        path = self.requests / f"{run_id}.request.json"
        if not path.absolute().is_relative_to(self.root):
            raise RuntimeError("Operator checkpoint path is invalid")
        return path

    @staticmethod
    def _invalid(run_id: str, reason: str) -> RuntimeError:
        _LOG.error("operator_checkpoint_rejected", extra={"run_id": run_id, "reason": reason})
        return RuntimeError(f"Operator checkpoint invalid: {reason}")

    def _read(self, run_id: str) -> tuple[dict[str, str], Path] | None:
        path = self._request_path(run_id)
        if path.is_symlink():
            raise self._invalid(run_id, "symlink request")
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > 4096:
            raise self._invalid(run_id, "request type or size")
        try:
            payload = json.loads(path.read_bytes())
            if not isinstance(payload, dict) or set(payload) != _FIELDS:
                raise ValueError
            values = {key: str(value) for key, value in payload.items()}
            target = RunState(values["target_state"])
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise self._invalid(run_id, "corrupt envelope") from error
        if values["schema"] != _SCHEMA or values["run_id"] != run_id:
            raise self._invalid(run_id, "schema or run binding")
        if not _REQUEST_ID.fullmatch(values["request_id"]):
            raise self._invalid(run_id, "request identity")
        if target not in _LEGAL_TARGETS:
            raise self._invalid(run_id, "illegal target state")
        content = {key: values[key] for key in _FIELDS - {"sha256"}}
        expected = sha256(_canonical(content)).hexdigest()
        if not hmac.compare_digest(values["sha256"], expected):
            raise self._invalid(run_id, "digest mismatch")
        return values, path

    @staticmethod
    def _fsync(directory: Path) -> None:
        descriptor = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def consume_at_target(self, run: RevenueAnalysisRun) -> bool:
        """Consume a valid request only at its committed target snapshot."""
        loaded = self._read(run.run_id)
        if loaded is None:
            return False
        payload, path = loaded
        target = RunState(payload["target_state"])
        if run.state is target:
            self.consumed.mkdir(parents=True, exist_ok=True)
            audit = self.consumed / f"{payload['sha256']}.json"
            if audit.exists():
                raise self._invalid(run.run_id, "request already consumed")
            os.replace(path, audit)
            self._fsync(self.requests)
            self._fsync(self.consumed)
            _LOG.info(
                "operator_checkpoint_consumed",
                extra={
                    "run_id": run.run_id,
                    "target_state": target,
                    "request_id": payload["request_id"],
                    "digest": payload["sha256"],
                },
            )
            return True
        if run.state not in _ORDER or _ORDER[run.state] > _ORDER[target]:
            raise self._invalid(run.run_id, "target precedes committed state")
        return False
