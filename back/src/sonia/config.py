"""Environment-backed application configuration."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings with safe local defaults."""

    app_name: str
    app_version: str
    environment: str
    host: str
    port: int
    log_level: str
    frontend_dir: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        """Build settings from `SONIA_*` environment variables."""
        port = int(os.getenv("SONIA_PORT", "8080"))
        if not 1 <= port <= 65535:
            raise ValueError("SONIA_PORT must be between 1 and 65535")

        return cls(
            app_name=os.getenv("SONIA_APP_NAME", "SON-IA"),
            app_version=os.getenv("SONIA_APP_VERSION", "0.1.0"),
            environment=os.getenv("SONIA_ENVIRONMENT", "development"),
            host=os.getenv("SONIA_HOST", "0.0.0.0"),
            port=port,
            log_level=os.getenv("SONIA_LOG_LEVEL", "INFO").upper(),
            frontend_dir=Path(os.getenv("SONIA_FRONTEND_DIR", "front")).resolve(),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance."""
    return Settings.from_environment()
