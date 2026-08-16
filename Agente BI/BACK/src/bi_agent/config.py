"""Environment-backed configuration for the standalone BI backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime settings with container-safe defaults."""

    host: str
    port: int
    log_level: str

    @classmethod
    def from_environment(cls) -> Settings:
        port = int(os.getenv("SONIA_PORT", "8080"))
        if not 1 <= port <= 65535:
            raise ValueError("SONIA_PORT debe estar entre 1 y 65535.")
        return cls(
            host=os.getenv("SONIA_HOST", "0.0.0.0"),
            port=port,
            log_level=os.getenv("SONIA_LOG_LEVEL", "INFO").upper(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()
