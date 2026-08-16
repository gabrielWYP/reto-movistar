"""Run the standalone Billing backend."""

import uvicorn

from .config import Settings


def main() -> None:
    settings = Settings.from_environment()
    uvicorn.run("billing_agent.app:app", host=settings.host, port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
