from sqlalchemy import text

from app.db.session import build_engine


def test_build_engine_executes_a_query() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")

    with engine.connect() as connection:
        assert connection.execute(text("SELECT 1")).scalar_one() == 1

    engine.dispose()
