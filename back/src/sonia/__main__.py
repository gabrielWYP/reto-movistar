"""Run the SON-IA API with development defaults."""

import uvicorn

from sonia.config import get_settings


def main() -> None:
    """Start the ASGI server using environment-backed settings."""
    settings = get_settings()
    uvicorn.run(
        "sonia.entrypoints.api:app",
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
