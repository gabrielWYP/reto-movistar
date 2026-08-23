"""Checksummed storage readiness, backup/restore, and quarantine."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from sonia.persistence.sqlite import DatasetRevision

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Artifact:
    """Path and digest for one immutable manifest."""

    path: Path
    sha256: str


@dataclass(frozen=True)
class Readiness:
    """Fail-closed storage verification outcome."""

    ready: bool
    issues: tuple[str, ...]
    quarantined: tuple[Path, ...]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        digest = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-")
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _envelope(payload: object) -> bytes:
    return _canonical({"payload": payload, "sha256": sha256(_canonical(payload)).hexdigest()})


def _read_envelope(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_bytes())
        payload = document["payload"]
        if not isinstance(payload, dict):
            raise ValueError
        if document["sha256"] != sha256(_canonical(payload)).hexdigest():
            raise ValueError
        return payload
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid or corrupt {label}") from error


class StorageHardener:
    """Harden one single-process SQLite and immutable-file storage root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.database = self.root / "db/sonia.sqlite3"

    @staticmethod
    def _safe(root: Path, value: str | Path) -> Path:
        candidate = Path(value)
        candidate = candidate if candidate.is_absolute() else root / candidate
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root) or candidate.is_symlink():
            raise ValueError(f"Path escapes storage root: {value}")
        return resolved

    def _datasets(self) -> tuple[DatasetRevision, ...]:
        if not self.database.is_file() or self.database.is_symlink():
            raise RuntimeError("Durable storage unavailable")
        try:
            with sqlite3.connect(self.database) as connection:
                rows = connection.execute("SELECT payload FROM datasets").fetchall()
            return tuple(DatasetRevision.model_validate_json(row[0]) for row in rows)
        except (sqlite3.DatabaseError, ValueError) as error:
            raise RuntimeError("Dataset catalogue is corrupt") from error

    def _destination(self, value: Path) -> Path:
        candidate = value.resolve()
        if value.absolute().is_relative_to(self.root) or candidate.is_relative_to(self.root):
            raise ValueError("Destination cannot be inside live storage")
        return candidate

    def verify(self) -> Readiness:
        """Verify referenced files and quarantine only proven dataset orphans."""
        issues: list[str] = []
        quarantined: list[Path] = []
        try:
            datasets = self._datasets()
        except RuntimeError as error:
            datasets = ()
            issues.append(str(error))
        referenced: set[Path] = set()
        for dataset in datasets:
            for item in dataset.files:
                try:
                    path = self._safe(self.root, item.path)
                    referenced.add(path)
                    if not path.is_file() or _digest(path) != item.sha256:
                        issues.append(f"Invalid dataset reference: {item.source}")
                except (OSError, ValueError) as error:
                    issues.append(str(error))
        dataset_root = self.root / "datasets"
        if datasets and dataset_root.exists():
            for path in (
                item for item in dataset_root.rglob("*") if item.is_file() or item.is_symlink()
            ):
                if path.is_symlink() or path.resolve() not in referenced:
                    target = self.root / "quarantine" / f"{time.time_ns()}-{path.name}"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(path, target)
                    audit = {
                        "original": str(path.relative_to(self.root)),
                        "quarantined": target.name,
                    }
                    _atomic(target.with_suffix(".audit.json"), _canonical(audit))
                    quarantined.append(target)
        outcome = Readiness(not issues, tuple(issues), tuple(quarantined))
        _LOG.info(
            "storage_readiness",
            extra={"ready": outcome.ready, "issues": len(issues), "quarantined": len(quarantined)},
        )
        return outcome

    def require_ready(self) -> None:
        """Freeze advancement whenever durable lineage is not verifiable."""
        outcome = self.verify()
        if not outcome.ready:
            raise RuntimeError("Storage readiness frozen: " + "; ".join(outcome.issues))

    def backup(self, destination: Path) -> Artifact:
        """Create a SQLite-consistent backup plus verified immutable files and manifest."""
        self.require_ready()
        destination = self._destination(destination)
        if destination.exists():
            raise FileExistsError(destination)
        destination.mkdir(parents=True)
        target_database = destination / "db/sonia.sqlite3"
        target_database.parent.mkdir(parents=True)
        with (
            sqlite3.connect(self.database) as source_db,
            sqlite3.connect(target_database) as target_db,
        ):
            source_db.backup(target_db)
        with target_database.open("rb") as stream:
            os.fsync(stream.fileno())
        files: list[dict[str, str]] = []
        for dataset in self._datasets():
            for item in dataset.files:
                source = self._safe(self.root, item.path)
                relative = source.relative_to(self.root)
                target = self._safe(destination, relative)
                _atomic(target, source.read_bytes())
                if _digest(target) != item.sha256:
                    raise RuntimeError("Backup dataset verification failed")
                files.append({"path": str(relative), "sha256": item.sha256})
        payload = {
            "version": 1,
            "database": {"path": "db/sonia.sqlite3", "sha256": _digest(target_database)},
            "files": files,
        }
        manifest = destination / "manifest.json"
        _atomic(manifest, _envelope(payload))
        _LOG.info("storage_backup", extra={"files": len(files), "outcome": "verified"})
        return Artifact(manifest, _digest(manifest))

    def restore(self, backup: Path, destination: Path) -> StorageHardener:
        """Validate and restore a backup into a fresh root without overwriting live storage."""
        backup, destination = backup.resolve(), self._destination(destination)
        if destination == self.root or destination.exists():
            raise FileExistsError(destination)
        payload = _read_envelope(self._safe(backup, "manifest.json"), "manifest")
        entries = [payload["database"], *payload["files"]]
        for entry in entries:
            source = self._safe(backup, entry["path"])
            if not source.is_file() or _digest(source) != entry["sha256"]:
                raise RuntimeError("Backup lineage verification failed")
            _atomic(self._safe(destination, entry["path"]), source.read_bytes())
        database = destination / "db/sonia.sqlite3"
        with sqlite3.connect(database) as connection:
            for (raw,) in connection.execute("SELECT payload FROM datasets").fetchall():
                dataset = DatasetRevision.model_validate_json(raw)
                files = tuple(
                    item.model_copy(
                        update={"path": destination / Path(item.path).relative_to(self.root)}
                    )
                    for item in dataset.files
                )
                restored = dataset.model_copy(update={"files": files})
                connection.execute(
                    "UPDATE datasets SET payload = ? WHERE revision_id = ?",
                    (restored.model_dump_json(), restored.revision_id),
                )
        hardener = StorageHardener(destination)
        hardener.require_ready()
        _LOG.info("storage_restore", extra={"files": len(entries), "outcome": "verified"})
        return hardener
