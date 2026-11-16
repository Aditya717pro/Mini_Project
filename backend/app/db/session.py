from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def build_engine(
    database_url: str,
    *,
    connect_timeout: int = 5,
    echo: bool = False,
) -> Engine:
    """Create the SQLAlchemy engine without opening a connection."""

    kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "echo": echo,
    }
    if database_url.startswith("mysql"):
        kwargs["connect_args"] = {"connect_timeout": connect_timeout}
    return create_engine(database_url, **kwargs)


engine = build_engine(
    settings.database_url,
    connect_timeout=settings.database_connect_timeout,
    echo=settings.sql_echo,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and always close it after the request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
