"""Neon Postgres connection. DATABASE_URL comes from the environment or crawler/.env.

This is the only place that reads the secret. Nothing else in the codebase
touches os.environ for the database — call get_engine() / get_database_url().
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# crawler/ (folder that contains data/, output/, src/, .env)
CRAWLER_ROOT = Path(__file__).resolve().parents[3]

# Load crawler/.env once (no-op if file or python-dotenv missing values).
load_dotenv(CRAWLER_ROOT / ".env")


def get_database_url(url: str | None = None) -> str | None:
    """Return the Postgres URL, or None if we should fall back to SQLite."""
    raw = url or os.environ.get("DATABASE_URL")
    if not raw:
        return None
    raw = raw.strip().strip("\"'")
    if not raw:
        return None
    # SQLAlchemy 2.0 needs an explicit driver: postgresql:// -> postgresql+psycopg://
    # (we install psycopg v3, not psycopg2).
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    if raw.startswith("postgresql://") and "+psycopg" not in raw.split("://", 1)[0]:
        raw = "postgresql+psycopg://" + raw[len("postgresql://"):]
    return raw


def masked_url(url: str) -> str:
    """Hide the password for logs / stats output."""
    try:
        parts = urlsplit(url)
        host = parts.hostname or "?"
        return f"{parts.scheme}://***@{host}/{parts.path.lstrip('/') or ''}"
    except Exception:
        return "postgres://***"


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    """Create (and cache) a SQLAlchemy engine for Neon."""
    db_url = get_database_url(url)
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to crawler/.env or the environment."
        )
    return create_engine(
        db_url,
        pool_pre_ping=True,  # Neon pooler drops idle conns; test before use
        pool_size=5,
        max_overflow=10,
        pool_recycle=300,
    )


def _unsplit_without_query(url: str) -> str:
    return urlunsplit(urlsplit(url)._replace(query=""))
