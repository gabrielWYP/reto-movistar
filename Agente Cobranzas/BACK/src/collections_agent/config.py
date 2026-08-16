"""Environment-backed settings scoped to the standalone collections agent."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _positive_int(name: str, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(os.getenv(name, str(default))), maximum))
    except ValueError:
        return default


def _text(name: str, default: str) -> str:
    """Return a trimmed environment value or its documented default."""
    return os.getenv(name, "").strip() or default


@dataclass(frozen=True, slots=True)
class CollectionsSettings:
    """Immutable runtime configuration for standalone and integrated modes."""

    host: str
    port: int
    log_level: str
    model: str
    reasoning_effort: str
    max_tool_calls: int
    max_output_tokens: int
    max_upload_bytes: int
    max_upload_files: int
    dataset_path: Path | None

    @classmethod
    def from_environment(cls) -> "CollectionsSettings":
        effort = _text("SONIA_COLLECTIONS_REASONING_EFFORT", "low").lower()
        if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            effort = "low"
        raw_dataset = os.getenv("SONIA_COLLECTIONS_DATASET", "").strip()
        return cls(
            host=_text("SONIA_HOST", "0.0.0.0"),
            port=_positive_int("SONIA_PORT", 8080, 65535),
            log_level=_text("SONIA_LOG_LEVEL", "INFO").upper(),
            model=_text("SONIA_COLLECTIONS_MODEL", "gpt-5.6-terra"),
            reasoning_effort=effort,
            max_tool_calls=_positive_int("SONIA_COLLECTIONS_MAX_TOOL_CALLS", 3, 5),
            max_output_tokens=_positive_int(
                "SONIA_COLLECTIONS_MAX_OUTPUT_TOKENS", 700, 2000
            ),
            max_upload_bytes=_positive_int(
                "SONIA_COLLECTIONS_MAX_UPLOAD_BYTES", 10 * 1024 * 1024, 50 * 1024 * 1024
            ),
            max_upload_files=_positive_int("SONIA_COLLECTIONS_MAX_UPLOAD_FILES", 6, 6),
            dataset_path=Path(raw_dataset).expanduser().resolve() if raw_dataset else None,
        )


@lru_cache(maxsize=1)
def get_settings() -> CollectionsSettings:
    """Return process-wide settings without scattering environment lookups."""
    return CollectionsSettings.from_environment()
