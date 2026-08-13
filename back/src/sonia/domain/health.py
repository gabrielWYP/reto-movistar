"""Health contract exposed by the application boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Public liveness payload without internal or secret data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"
    service: str
    version: str
    environment: str
