"""Tiny additive schema migrations for SQLite.

`SQLModel.metadata.create_all` creates new tables but never adds columns to existing ones. Each entry
below adds one column to a table created by an earlier version, with a safe default, so existing
databases keep working after an upgrade. Only additive changes are allowed here.
"""

from sqlalchemy import Engine

# (table, column, SQL type + default)
COLUMNS: list[tuple[str, str, str]] = [
    ("chunk", "kind", "VARCHAR NOT NULL DEFAULT 'text'"),
    ("job", "lesson_id", "INTEGER"),
]


def apply(engine: Engine) -> list[str]:
    added = []
    with engine.begin() as conn:
        for table, column, ddl in COLUMNS:
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if existing and column not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
                conn.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column})")
                added.append(f"{table}.{column}")
    return added
