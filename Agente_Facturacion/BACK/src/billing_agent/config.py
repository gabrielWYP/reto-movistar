"""Environment-backed backend settings."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "INFO"
    dataset_path: Path | None = None
    upload_root: Path = Path(tempfile.gettempdir()) / "sonia-billing"
    max_upload_bytes: int = 20 * 1024 * 1024
    max_uncompressed_bytes: int = 48 * 1024 * 1024
    max_upload_files: int = 5
    dataset_ttl_seconds: int = 4 * 60 * 60

    @classmethod
    def from_environment(cls) -> "Settings":
        dataset = os.getenv("SONIA_DATASET", "").strip()
        port = int(os.getenv("SONIA_PORT", "8080"))
        if not 1 <= port <= 65535:
            raise ValueError("SONIA_PORT debe estar entre 1 y 65535.")
        return cls(
            host=os.getenv("SONIA_HOST", "0.0.0.0"),
            port=port,
            log_level=os.getenv("SONIA_LOG_LEVEL", "INFO").upper(),
            dataset_path=Path(dataset).expanduser().resolve() if dataset else None,
            upload_root=Path(os.getenv("SONIA_UPLOAD_ROOT", str(Path(tempfile.gettempdir()) / "sonia-billing"))).resolve(),
            max_upload_bytes=int(os.getenv("SONIA_MAX_UPLOAD_MB", "20")) * 1024 * 1024,
            max_uncompressed_bytes=int(os.getenv("SONIA_MAX_UNCOMPRESSED_MB", "48")) * 1024 * 1024,
            max_upload_files=int(os.getenv("SONIA_MAX_UPLOAD_FILES", "5")),
            dataset_ttl_seconds=int(os.getenv("SONIA_DATASET_TTL_SECONDS", str(4 * 60 * 60))),
        )
