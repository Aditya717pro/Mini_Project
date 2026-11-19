from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app
from app.models import Base


@pytest.fixture()
def app(tmp_path) -> FastAPI:
    return create_app(
        Settings(
            environment="test",
            log_level="WARNING",
            cors_origins=["http://localhost:5173"],
            database_url="sqlite://",
            raw_storage_dir=tmp_path / "raw",
            processed_storage_dir=tmp_path / "processed",
            synthmed_storage_dir=tmp_path / "synthmed",
            synthmed_generation_inline=True,
        )
    )


@pytest.fixture()
def db_session(app: FastAPI) -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = factory()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client
