import logging
from time import perf_counter
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_db
from app.schemas.health import HealthResponse, ReadinessResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def liveness(request: Request) -> HealthResponse:
    """Report that the API process is running. Does not check dependencies."""

    settings: Settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    responses={503: {"model": ReadinessResponse, "description": "A dependency is unavailable"}},
)
def readiness(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> ReadinessResponse:
    """Probe the database and report readiness.

    Returns HTTP 503 when the database cannot be reached so orchestrators can
    withhold traffic without restarting the process.
    """

    started = perf_counter()
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        latency_ms = round((perf_counter() - started) * 1000, 2)
        logger.warning("Database readiness probe failed: %s", error)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="degraded",
            database="unavailable",
            latency_ms=latency_ms,
            detail="Database connection failed.",
        )

    latency_ms = round((perf_counter() - started) * 1000, 2)
    return ReadinessResponse(
        status="ready",
        database="ok",
        latency_ms=latency_ms,
    )
