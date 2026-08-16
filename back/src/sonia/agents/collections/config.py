"""Environment-backed settings scoped to the collections module."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(os.getenv(name, str(default))), maximum))
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class CollectionsSettings:
    """Agent-only configuration; platform host and port remain in sonia.config."""

    model: str
    reasoning_effort: str
    max_tool_calls: int
    max_output_tokens: int
    max_upload_bytes: int
    max_upload_files: int
    dataset_path: Path | None

    @classmethod
    def from_environment(cls) -> "CollectionsSettings":
        effort = os.getenv("SONIA_COLLECTIONS_REASONING_EFFORT", "low").lower()
        if effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            effort = "low"
        raw_dataset = os.getenv("SONIA_COLLECTIONS_DATASET", "").strip()
        return cls(
            model=os.getenv("SONIA_COLLECTIONS_MODEL", "gpt-5.6-terra"),
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
