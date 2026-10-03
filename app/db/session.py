from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine

from app.db import models  # noqa: F401  (registers tables)


def make_engine(db_path: Path | str) -> Engine:
    """Create the SQLite engine and tables. Pass ':memory:' for tests."""
    url = "sqlite://" if str(db_path) == ":memory:" else f"sqlite:///{db_path}"
    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if url == "sqlite://":
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    SQLModel.metadata.create_all(engine)
    return engine
