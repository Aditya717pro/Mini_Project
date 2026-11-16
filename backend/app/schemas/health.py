from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="Liveness status.")
    service: str = Field(description="Service name.")
    version: str = Field(description="Application version.")
    environment: str = Field(description="Deployment environment.")


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"] = Field(description="Overall readiness status.")
    database: Literal["ok", "unavailable"] = Field(
        description="Database connectivity status."
    )
    latency_ms: float = Field(description="Database probe latency in milliseconds.")
    detail: str | None = Field(default=None, description="Optional failure detail.")
