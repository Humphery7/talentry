"""Persist jobs. SQLite for tests/offline, Neon Postgres when DATABASE_URL is set.

`JobStore(path)` is a factory: explicit *.db paths always use SQLite
(tests), otherwise DATABASE_URL in crawler/.env routes to Postgres.
Only storage/ knows which backend is active; pipeline/ and cli/ are unchanged.
"""

from __future__ import annotations

from pathlib import Path


def JobStore(path: Path | str | None = None):  # noqa: N802 — keeps old call sites working
    """Return a SQLite or Postgres store with the same API."""
    from .db import get_database_url
    from .sqlite import JobStore as SqliteJobStore

    text = str(path) if path is not None else ""
    if text.startswith(("postgres://", "postgresql://")):
        from .postgres import PostgresJobStore

        return PostgresJobStore(text)
    if text.endswith((".db", ".sqlite", ".sqlite3")):
        return SqliteJobStore(path)
    if get_database_url():
        from .postgres import PostgresJobStore

        return PostgresJobStore()
    return SqliteJobStore(path)


__all__ = ["JobStore"]
