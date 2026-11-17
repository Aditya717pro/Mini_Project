from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db


class HealthySession:
    def execute(self, statement: Any) -> None:
        return None


class UnhealthySession:
    def execute(self, statement: Any) -> None:
        raise SQLAlchemyError("database offline")


def override_db(app: FastAPI, session: object) -> None:
    app.dependency_overrides[get_db] = lambda: session


def test_root_endpoint(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "MedDataHub API",
        "version": "0.2.0",
        "environment": "test",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


def test_liveness_does_not_require_database(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "MedDataHub API",
        "version": "0.2.0",
        "environment": "test",
    }


def test_request_id_is_generated(client: TestClient) -> None:
    first = client.get("/api/v1/health")
    second = client.get("/api/v1/health")

    assert len(first.headers["X-Request-ID"]) == 32
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "test-request-123"},
    )

    assert response.headers["X-Request-ID"] == "test-request-123"


def test_readiness_reports_database_ok(
    app: FastAPI,
    client: TestClient,
) -> None:
    override_db(app, HealthySession())

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert isinstance(body["latency_ms"], (int, float))
    assert body["detail"] is None


def test_readiness_returns_503_when_database_is_unavailable(
    app: FastAPI,
    client: TestClient,
) -> None:
    override_db(app, UnhealthySession())

    response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
    assert isinstance(body["latency_ms"], (int, float))
    assert body["detail"] == "Database connection failed."


def test_cors_allows_configured_frontend_origin(client: TestClient) -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_openapi_lists_health_endpoints(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/health" in paths
    assert "/api/v1/health/ready" in paths
