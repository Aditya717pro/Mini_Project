import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.v1 import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info(
        "Starting %s v%s in %s mode",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )
    yield
    engine.dispose()
    logger.info("MedDataHub API stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application. Settings can be injected for tests."""

    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    app = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        description=(
            "API for an AI-ready medical dataset repository supporting women's, "
            "maternal and paediatric health research. Includes authentication, governed "
            "uploads, guarded ETL, quality, readiness, representativeness and access workflows."
        ),
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = app_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next) -> Response:
        incoming = request.headers.get("X-Request-ID", "").strip()
        request_id = incoming if 0 < len(incoming) <= 128 else uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(api_router, prefix=app_settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": app_settings.app_name,
            "version": app_settings.app_version,
            "environment": app_settings.environment,
            "docs": "/docs",
            "health": f"{app_settings.api_v1_prefix}/health",
        }

    return app


app = create_app()
