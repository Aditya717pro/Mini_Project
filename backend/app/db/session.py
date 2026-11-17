from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.connection import build_engine, build_session_factory

settings = get_settings()

engine = build_engine(
    settings.database_url,
    connect_timeout=settings.database_connect_timeout,
    echo=settings.sql_echo,
)

SessionLocal = build_session_factory(engine)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and always close it after the request."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
