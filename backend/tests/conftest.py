from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture()
def app() -> FastAPI:
    return create_app(
        Settings(
            environment="test",
            log_level="WARNING",
            cors_origins=["http://localhost:5173"],
        )
    )


@pytest.fixture()
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
