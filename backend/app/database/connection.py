from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def build_engine(
    database_url: str,
    *,
    connect_timeout: int = 5,
    echo: bool = False,
) -> Engine:
    """Create an engine without opening a connection.

    SQLite is supported for tests and local development. Production deployments
    should supply a MySQL URL through the DATABASE_URL environment variable.
    """

    kwargs: dict[str, Any] = {
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "echo": echo,
    }
    if database_url.startswith("mysql"):
        kwargs["connect_args"] = {"connect_timeout": connect_timeout}
    return create_engine(database_url, **kwargs)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
