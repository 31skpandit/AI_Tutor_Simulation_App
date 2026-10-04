from pathlib import Path

from sqlalchemy import Engine, event
from sqlmodel import SQLModel, create_engine

from app.db import migrations, models  # noqa: F401  (models registers tables)


def _sqlite_pragmas(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")  # wait up to 10 s if the background worker is writing
    cursor.close()


def make_engine(db_path: Path | str) -> Engine:
    """Create the SQLite engine and tables. Pass ':memory:' for tests."""
    url = "sqlite://" if str(db_path) == ":memory:" else f"sqlite:///{db_path}"
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url == "sqlite://":
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    event.listen(engine, "connect", _sqlite_pragmas)
    if url != "sqlite://":
        with engine.connect() as conn:  # WAL: the UI can read while the worker writes
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
    SQLModel.metadata.create_all(engine)
    migrations.apply(engine)  # add columns introduced after the database was created
    return engine
