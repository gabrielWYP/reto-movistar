"""Append-only, tamper-evident record of every model call inside one run.

One gzipped JSON Lines object per run: lines concatenate, so nothing has to be
read back to append, and each line seals the previous one by digest. Editing a
line in the middle invalidates every line after it.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import UTC, datetime
from hashlib import sha256
from threading import Lock
from typing import Any

from sonia.integrations.object_store import ObjectStore

logger = logging.getLogger(__name__)

CONTENT_TYPE = "application/gzip"
MAX_TEXT_LENGTH = 8000
MAX_RECORDS_PER_RUN = 500
_TEXT_FIELDS = ("question", "answer", "detail")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _bounded(entry: dict[str, Any]) -> dict[str, Any]:
    """Keep the object small; a model can return far more prose than an audit needs."""
    trimmed = dict(entry)
    for field in _TEXT_FIELDS:
        value = trimmed.get(field)
        if isinstance(value, str) and len(value) > MAX_TEXT_LENGTH:
            trimmed[field] = value[:MAX_TEXT_LENGTH]
            trimmed[f"{field}_truncated_from"] = len(value)
    return trimmed


class RunAuditLog:
    """Buffer one run's model calls and publish them as a single sealed object."""

    def __init__(self, store: ObjectStore, prefix: str = "audit") -> None:
        self._store, self._prefix = store, prefix
        self._buffers: dict[str, list[dict[str, Any]]] = {}
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self._store.configured

    def record(self, run_id: str, entry: dict[str, Any]) -> None:
        """Chain one model call onto this run's record."""
        if not self.enabled:
            return
        with self._lock:
            buffer = self._buffers.setdefault(run_id, [])
            if len(buffer) >= MAX_RECORDS_PER_RUN:
                return
            previous = buffer[-1]["sha256"] if buffer else None
            sealed = _bounded(entry) | {
                "run_id": run_id,
                "recorded_at": datetime.now(UTC).isoformat(),
                "sequence": len(buffer),
                "prev_sha256": previous,
            }
            buffer.append(sealed | {"sha256": sha256(_canonical(sealed)).hexdigest()})

    def pending(self, run_id: str) -> int:
        with self._lock:
            return len(self._buffers.get(run_id, ()))

    def publish(self, run_id: str) -> str | None:
        """Compress and store the sealed record, then release the buffer."""
        if not self.enabled:
            return None
        with self._lock:
            records = self._buffers.pop(run_id, [])
        if not records:
            return None
        body = gzip.compress(b"\n".join(_canonical(record) for record in records) + b"\n", mtime=0)
        key = f"{self._prefix}/{datetime.now(UTC):%Y/%m/%d}/{run_id}.jsonl.gz"
        try:
            url = self._store.put(key, body, CONTENT_TYPE)
        except RuntimeError:
            logger.exception("run_audit_publish_failed", extra={"run_id": run_id, "key": key})
            return None
        logger.info(
            "run_audit_published",
            extra={"run_id": run_id, "key": key, "records": len(records), "bytes": len(body)},
        )
        return url


def verify_chain(records: list[dict[str, Any]]) -> bool:
    """Recompute every seal; used by tests and by anyone auditing a stored object."""
    previous: str | None = None
    for record in records:
        body = {key: value for key, value in record.items() if key != "sha256"}
        if body.get("prev_sha256") != previous:
            return False
        if sha256(_canonical(body)).hexdigest() != record.get("sha256"):
            return False
        previous = record["sha256"]
    return True
