"""Neon Postgres store. Same tables + same API as storage/sqlite.py.

Two tables:
  companies  one row per employer       (from data/companies.csv)
  jobs       one row per job posting    (found by the crawl)
  meta       key/value (companies_hash for skip-if-unchanged)

A job is never deleted. When it disappears from its career page it is marked
status='closed', and if it comes back it is marked 'open' again.

Only this file + db.py know about Postgres. pipeline/ and cli/ call the same
methods as before (save_companies / save_board_jobs / stats / sample / close).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from talentry_crawler.models import Board, Company, Job

from .db import get_database_url, get_engine, masked_url
from .sqlite import _companies_fingerprint, _embedding_or_none, _stored_description

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS companies (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    website TEXT,
    logo_url TEXT,
    icon_url TEXT,
    industry TEXT,
    employee_count_range TEXT,
    founded_year INTEGER
);

CREATE TABLE IF NOT EXISTS jobs (
    url TEXT PRIMARY KEY,
    company_slug TEXT NOT NULL,
    board_slug TEXT NOT NULL,
    monitor_type TEXT NOT NULL,
    title TEXT,
    description TEXT,
    locations_json TEXT,
    employment_type TEXT,
    workplace_type TEXT,
    date_posted TEXT,
    salary_json TEXT,
    metadata_json TEXT,
    seniority TEXT,
    occupation TEXT,
    technologies_json TEXT,
    embedding vector(384),
    embedding_text_hash TEXT,
    embedding_updated_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'open',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_slug);
CREATE INDEX IF NOT EXISTS idx_jobs_board ON jobs(board_slug);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_embedding
    ON jobs USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

SAVE_COMPANY = """
INSERT INTO companies (
    slug, name, website, logo_url, icon_url,
    industry, employee_count_range, founded_year
) VALUES (
    :slug, :name, :website, :logo_url, :icon_url,
    :industry, :employee_count_range, :founded_year
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    website = EXCLUDED.website,
    logo_url = EXCLUDED.logo_url,
    icon_url = EXCLUDED.icon_url,
    industry = EXCLUDED.industry,
    employee_count_range = EXCLUDED.employee_count_range,
    founded_year = EXCLUDED.founded_year
"""

# Insert a job, or refresh it if we already have it (same url).
# first_seen_at is deliberately not in the UPDATE list: it keeps the original date.
SAVE_JOB = """
INSERT INTO jobs (
    url, company_slug, board_slug, monitor_type,
    title, description, locations_json, employment_type, workplace_type,
    date_posted, salary_json, metadata_json,
    seniority, occupation, technologies_json,
    embedding, embedding_text_hash, embedding_updated_at,
    status, first_seen_at, last_seen_at
) VALUES (
    :url, :company_slug, :board_slug, :monitor_type,
    :title, :description, :locations_json, :employment_type, :workplace_type,
    :date_posted, :salary_json, :metadata_json,
    :seniority, :occupation, :technologies_json,
    CAST(:embedding AS vector), :embedding_text_hash,
    CAST(:embedding_updated_at AS timestamptz),
    'open', :now, :now
)
ON CONFLICT (url) DO UPDATE SET
    company_slug = EXCLUDED.company_slug,
    board_slug = EXCLUDED.board_slug,
    monitor_type = EXCLUDED.monitor_type,
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    locations_json = EXCLUDED.locations_json,
    employment_type = EXCLUDED.employment_type,
    workplace_type = EXCLUDED.workplace_type,
    date_posted = EXCLUDED.date_posted,
    salary_json = EXCLUDED.salary_json,
    metadata_json = EXCLUDED.metadata_json,
    seniority = EXCLUDED.seniority,
    occupation = EXCLUDED.occupation,
    technologies_json = EXCLUDED.technologies_json,
    embedding = COALESCE(EXCLUDED.embedding, jobs.embedding),
    embedding_text_hash = COALESCE(EXCLUDED.embedding_text_hash, jobs.embedding_text_hash),
    embedding_updated_at = COALESCE(EXCLUDED.embedding_updated_at, jobs.embedding_updated_at)
-- Only rewrite a row when something the ATS/labeler produced actually changed.
-- Rewriting every description on every crawl was generating hundreds of MB of
-- WAL and dead TOAST data (Neon counts that against the project size limit).
WHERE
    jobs.company_slug IS DISTINCT FROM EXCLUDED.company_slug
    OR jobs.board_slug IS DISTINCT FROM EXCLUDED.board_slug
    OR jobs.monitor_type IS DISTINCT FROM EXCLUDED.monitor_type
    OR jobs.title IS DISTINCT FROM EXCLUDED.title
    OR jobs.description IS DISTINCT FROM EXCLUDED.description
    OR jobs.locations_json IS DISTINCT FROM EXCLUDED.locations_json
    OR jobs.employment_type IS DISTINCT FROM EXCLUDED.employment_type
    OR jobs.workplace_type IS DISTINCT FROM EXCLUDED.workplace_type
    OR jobs.date_posted IS DISTINCT FROM EXCLUDED.date_posted
    OR jobs.salary_json IS DISTINCT FROM EXCLUDED.salary_json
    OR jobs.metadata_json IS DISTINCT FROM EXCLUDED.metadata_json
    OR jobs.seniority IS DISTINCT FROM EXCLUDED.seniority
    OR jobs.occupation IS DISTINCT FROM EXCLUDED.occupation
    OR jobs.technologies_json IS DISTINCT FROM EXCLUDED.technologies_json
    OR (
        EXCLUDED.embedding_text_hash IS NOT NULL
        AND jobs.embedding_text_hash IS DISTINCT FROM EXCLUDED.embedding_text_hash
    )
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_or_none(value) -> str | None:
    return json.dumps(value) if value else None


class PostgresJobStore:
    """JobStore backed by Neon Postgres. Same method names as the SQLite one."""

    def __init__(self, url: str | None = None) -> None:
        db_url = get_database_url(url)
        if not db_url:
            raise RuntimeError("DATABASE_URL is not set (crawler/.env).")
        self._url = db_url
        self._label = masked_url(db_url)
        self._engine: Engine = get_engine(db_url)
        with self._engine.begin() as conn:
            for stmt in SCHEMA.split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(text(stmt))

    # ---- writing ---------------------------------------------------------

    def save_companies(self, companies: list[Company]) -> bool:
        """Upsert companies, skip if hash unchanged. True if written."""
        fingerprint = _companies_fingerprint(companies)
        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT value FROM meta WHERE key = 'companies_hash'")
            ).fetchone()
            current = row[0] if row else None
            if current == fingerprint:
                return False
            if companies:
                conn.execute(
                    text(SAVE_COMPANY),
                    [
                        {
                            "slug": c.slug,
                            "name": c.name,
                            "website": c.website,
                            "logo_url": c.logo_url,
                            "icon_url": c.icon_url,
                            "industry": c.industry,
                            "employee_count_range": c.employee_count_range,
                            "founded_year": c.founded_year,
                        }
                        for c in companies
                    ],
                )
            conn.execute(
                text(
                    "INSERT INTO meta (key, value) VALUES ('companies_hash', :v) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
                ),
                {"v": fingerprint},
            )
            return True

    def save_board_jobs(self, board: Board, jobs: list[Job]) -> tuple[int, int, int]:
        """Save everything one board returned. Returns (inserted, updated, closed).

        Call only after a SUCCESSFUL fetch.
        """
        now = _now()
        urls = {job.url for job in jobs}
        with self._engine.begin() as conn:
            known_rows = conn.execute(
                text("SELECT url FROM jobs WHERE board_slug = :b"),
                {"b": board.board_slug},
            ).fetchall()
            known = {r[0] for r in known_rows}

            if jobs:
                conn.execute(
                    text(SAVE_JOB),
                    [
                        {
                            "url": job.url,
                            "company_slug": board.company_slug,
                            "board_slug": board.board_slug,
                            "monitor_type": board.monitor_type,
                            "title": job.title,
                            "description": _stored_description(job.description),
                            "locations_json": _json_or_none(job.locations),
                            "employment_type": job.employment_type,
                            "workplace_type": job.workplace_type,
                            "date_posted": job.date_posted,
                            "salary_json": _json_or_none(job.salary),
                            "metadata_json": _json_or_none(job.metadata),
                            "seniority": job.seniority,
                            "occupation": job.occupation,
                            "technologies_json": _json_or_none(job.technologies),
                            "embedding": _embedding_or_none(job.embedding),
                            "embedding_text_hash": job.embedding_text_hash,
                            "embedding_updated_at": now if job.embedding else None,
                            "now": now,
                        }
                        for job in jobs
                    ],
                )
            # SAVE_JOB skips unchanged content, so mark every job we saw as seen
            # in a cheap second pass. This keeps last_seen_at (and therefore the
            # close step below) accurate without rewriting descriptions.
            if urls:
                conn.execute(
                    text(
                        "UPDATE jobs SET last_seen_at = :now, status = 'open', closed_at = NULL "
                        "WHERE board_slug = :b AND url = ANY(:urls)"
                    ),
                    {"now": now, "b": board.board_slug, "urls": sorted(urls)},
                )
            closed = conn.execute(
                text(
                    "UPDATE jobs SET status = 'closed', closed_at = :now "
                    "WHERE board_slug = :b AND status = 'open' AND last_seen_at < :now"
                ),
                {"now": now, "b": board.board_slug},
            ).rowcount or 0

        return len(urls - known), len(urls & known), int(closed)

    def embedding_hashes(self, board: Board) -> dict[str, str]:
        """Return the embedding-text hash already stored for each job on a board."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT url, embedding_text_hash FROM jobs "
                    "WHERE board_slug = :b AND embedding_text_hash IS NOT NULL"
                ),
                {"b": board.board_slug},
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    # ---- reading (used by the CLI) ---------------------------------------

    def stats(self) -> dict[str, int | str]:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT "
                    "COUNT(*) FILTER (WHERE status = 'open') AS open_jobs, "
                    "COUNT(*) FILTER (WHERE status = 'closed') AS closed_jobs, "
                    "COUNT(DISTINCT company_slug) AS companies_with_jobs, "
                    "COUNT(DISTINCT board_slug) AS boards "
                    "FROM jobs"
                )
            ).mappings().fetchone() or {}
            companies = conn.execute(text("SELECT COUNT(*) FROM companies")).fetchone()
        return {
            "db": self._label,
            "open_jobs": int(row.get("open_jobs", 0) or 0),
            "closed_jobs": int(row.get("closed_jobs", 0) or 0),
            "companies_with_jobs": int(row.get("companies_with_jobs", 0) or 0),
            "boards": int(row.get("boards", 0) or 0),
            "companies_loaded": int(companies[0] if companies else 0),
        }

    def sample(self, n: int = 5) -> list[dict]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT c.name AS company, j.title, j.seniority, j.occupation, "
                    "j.technologies_json, j.locations_json, j.url "
                    "FROM jobs j LEFT JOIN companies c ON c.slug = j.company_slug "
                    "WHERE j.status = 'open' "
                    "ORDER BY j.last_seen_at DESC LIMIT :n"
                ),
                {"n": n},
            ).mappings().fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._engine.dispose()
