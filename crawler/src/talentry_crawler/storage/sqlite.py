"""Save companies and jobs in a local SQLite file (output/jobs.db).

Two tables:
  companies  one row per employer       (from data/companies.csv)
  jobs       one row per job posting    (found by the crawl)

A job is never deleted. When it disappears from its career page it is marked
status='closed', and if it comes back it is marked 'open' again.

The same two tables map 1:1 to Postgres later; only this file changes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from talentry_crawler.config.paths import OUTPUT_DIR
from talentry_crawler.models import MONITORS_WITHOUT_CLOSE, Board, Company, Job

DEFAULT_DB = OUTPUT_DIR / "jobs.db"

# Job descriptions are the bulk of the database. The embedding step already
# truncates at 4,000 chars; this keeps a longer copy for the job page without
# letting a few huge HTML pages dominate storage.
MAX_STORED_DESCRIPTION = 8_000


def _stored_description(description: str | None) -> str | None:
    if not description:
        return None
    return description[:MAX_STORED_DESCRIPTION]


def _json_list(raw: str | None) -> list[str]:
    """Read a JSON list column; a damaged value just means 'no locations'."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


SCHEMA = """
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
    external_id TEXT,
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
    embedding_json TEXT,
    embedding_text_hash TEXT,
    embedding_updated_at TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_slug);
CREATE INDEX IF NOT EXISTS idx_jobs_board ON jobs(board_slug);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
-- One row per provider posting, even when several searches report it under
-- different publisher URLs (JSearch's job_uid). NULLs are free to repeat.
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_external_id
    ON jobs(external_id) WHERE external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

# Insert a job, or refresh it if we already have it (same url).
# first_seen_at is deliberately not in the UPDATE list: it keeps the original date.
SAVE_JOB = """
INSERT INTO jobs (
    url, external_id, company_slug, board_slug, monitor_type,
    title, description, locations_json, employment_type, workplace_type,
    date_posted, salary_json, metadata_json,
    seniority, occupation, technologies_json,
    embedding_json, embedding_text_hash, embedding_updated_at,
    status, first_seen_at, last_seen_at
) VALUES (
    :url, :external_id, :company_slug, :board_slug, :monitor_type,
    :title, :description, :locations_json, :employment_type, :workplace_type,
    :date_posted, :salary_json, :metadata_json,
    :seniority, :occupation, :technologies_json,
    :embedding_json, :embedding_text_hash, :embedding_updated_at,
    'open', :now, :now
)
ON CONFLICT(url) DO UPDATE SET
    external_id = COALESCE(excluded.external_id, jobs.external_id),
    company_slug = excluded.company_slug,
    board_slug = excluded.board_slug,
    monitor_type = excluded.monitor_type,
    title = excluded.title,
    description = excluded.description,
    locations_json = excluded.locations_json,
    employment_type = excluded.employment_type,
    workplace_type = excluded.workplace_type,
    date_posted = excluded.date_posted,
    salary_json = excluded.salary_json,
    metadata_json = excluded.metadata_json,
    seniority = excluded.seniority,
    occupation = excluded.occupation,
    technologies_json = excluded.technologies_json,
    embedding_json = COALESCE(excluded.embedding_json, jobs.embedding_json),
    embedding_text_hash = COALESCE(excluded.embedding_text_hash, jobs.embedding_text_hash),
    embedding_updated_at = COALESCE(excluded.embedding_updated_at, jobs.embedding_updated_at)
-- Only rewrite a row when something the ATS/labeler produced actually changed.
-- Rewriting every description on every crawl was generating hundreds of MB of
-- WAL and dead TOAST data (Neon counts that against the project size limit).
WHERE
    jobs.external_id IS NOT excluded.external_id
    OR jobs.company_slug IS NOT excluded.company_slug
    OR jobs.board_slug IS NOT excluded.board_slug
    OR jobs.monitor_type IS NOT excluded.monitor_type
    OR jobs.title IS NOT excluded.title
    OR jobs.description IS NOT excluded.description
    OR jobs.locations_json IS NOT excluded.locations_json
    OR jobs.employment_type IS NOT excluded.employment_type
    OR jobs.workplace_type IS NOT excluded.workplace_type
    OR jobs.date_posted IS NOT excluded.date_posted
    OR jobs.salary_json IS NOT excluded.salary_json
    OR jobs.metadata_json IS NOT excluded.metadata_json
    OR jobs.seniority IS NOT excluded.seniority
    OR jobs.occupation IS NOT excluded.occupation
    OR jobs.technologies_json IS NOT excluded.technologies_json
    OR (
        excluded.embedding_text_hash IS NOT NULL
        AND jobs.embedding_text_hash IS NOT excluded.embedding_text_hash
    )
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_or_none(value) -> str | None:
    return json.dumps(value) if value else None


def _embedding_or_none(value: list[float] | None) -> str | None:
    if not value:
        return None
    return json.dumps(value, separators=(",", ":"))


def _chunked(values: list[str], size: int = 500) -> list[list[str]]:
    """Keep SQLite's bound-variable count under its limit."""
    return [values[i : i + size] for i in range(0, len(values), size)]


def _companies_fingerprint(companies: list[Company]) -> str:
    """Stable hash of the company list. Changes iff any field changes."""
    hasher = hashlib.sha256()
    for c in sorted(companies, key=lambda c: c.slug):
        hasher.update(
            json.dumps(
                [
                    c.slug,
                    c.name,
                    c.website,
                    c.logo_url,
                    c.icon_url,
                    c.industry,
                    c.employee_count_range,
                    c.founded_year,
                ],
                sort_keys=True,
            ).encode("utf-8")
        )
    return hasher.hexdigest()


class JobStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_DB
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._refuse_old_database()
        self._add_missing_columns()
        self._conn.executescript(SCHEMA)

    def _refuse_old_database(self) -> None:
        """An older version of the crawler made a jobs table without 'status'."""
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(jobs)")}
        if columns and "status" not in columns:
            raise RuntimeError(
                f"{self.path} was created by an older version of the crawler. "
                "Delete that file and run again (it only holds crawled jobs, which are quick to re-fetch)."
            )

    def _add_missing_columns(self) -> None:
        """Additive only, so an existing output/jobs.db keeps working."""
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(jobs)")}
        if columns and "external_id" not in columns:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN external_id TEXT")

    # ---- writing -------------------------------------------------------------

    def save_companies(self, companies: list[Company]) -> bool:
        """Upsert companies, but skip the write if nothing changed.

        companies.csv is static until manually edited, so we hash the list
        and store it in `meta`. Same hash as last time -> no SQL writes.
        Returns True if rows were written, False if skipped.
        """
        fingerprint = _companies_fingerprint(companies)
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'companies_hash'"
        ).fetchone()
        if row is not None and row["value"] == fingerprint:
            return False

        rows = [
            (
                c.slug, c.name, c.website, c.logo_url, c.icon_url,
                c.industry, c.employee_count_range, c.founded_year,
            )
            for c in companies
        ]
        with self._conn:
            self._conn.executemany("INSERT OR REPLACE INTO companies VALUES (?,?,?,?,?,?,?,?)", rows)
            self._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('companies_hash', ?)",
                (fingerprint,),
            )
        return True

    def save_board_jobs(self, board: Board, jobs: list[Job]) -> tuple[int, int, int]:
        """Save everything one board returned. Returns (inserted, updated, closed).

        Call this only after a SUCCESSFUL fetch: any job of this board that is not
        in `jobs` is treated as gone and marked closed.
        """
        now = _now()
        urls = {job.url for job in jobs}
        known = {
            row["url"]
            for row in self._conn.execute(
                "SELECT url FROM jobs WHERE board_slug = ?", (board.board_slug,)
            )
        }
        rows = [
            {
                "url": job.url,
                "external_id": job.external_id,
                "company_slug": job.company_slug or board.company_slug,
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
                "embedding_json": _embedding_or_none(job.embedding),
                "embedding_text_hash": job.embedding_text_hash,
                "embedding_updated_at": now if job.embedding else None,
                "now": now,
            }
            for job in jobs
        ]
        employers = {
            job.company_slug: (
                job.company_slug,
                job.company_name,
                job.company_website,
                job.company_logo_url,
            )
            for job in jobs
            if job.company_slug and job.company_name
        }

        with self._conn:  # one transaction: all of it is saved, or none of it
            if employers:
                # Aggregated postings carry their own employer. Never overwrite
                # curated company data (name, industry, ...) with a scrape.
                self._conn.executemany(
                    """
                    INSERT INTO companies (slug, name, website, logo_url)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(slug) DO UPDATE SET
                        website = COALESCE(companies.website, excluded.website),
                        logo_url = COALESCE(companies.logo_url, excluded.logo_url)
                    """,
                    list(employers.values()),
                )
            self._conn.executemany(SAVE_JOB, rows)
            # SAVE_JOB skips unchanged content, so mark every job we saw as seen
            # in a cheap second pass. This keeps last_seen_at (and therefore the
            # close step below) accurate without rewriting descriptions.
            for chunk in _chunked(sorted(urls)):
                placeholders = ",".join("?" * len(chunk))
                self._conn.execute(
                    f"""
                    UPDATE jobs SET last_seen_at = ?, status = 'open', closed_at = NULL
                    WHERE board_slug = ? AND url IN ({placeholders})
                    """,
                    (now, board.board_slug, *chunk),
                )
            # Everything we just saw has last_seen_at == now. Anything older was not on the page.
            # Search-backed sources (JSearch) only return a page of hits, so a job
            # missing today is not gone; the 30-day stale purge handles those.
            if board.monitor_type in MONITORS_WITHOUT_CLOSE:
                return len(urls - known), len(urls & known), 0
            closed = self._conn.execute(
                """
                UPDATE jobs SET status = 'closed', closed_at = ?
                WHERE board_slug = ? AND status = 'open' AND last_seen_at < ?
                """,
                (now, board.board_slug, now),
            ).rowcount

        return len(urls - known), len(urls & known), closed

    def touch_urls(self, urls: list[str]) -> int:
        """Refresh jobs we already have under another search/board.

        Used when a search returns a posting we stored before (same external
        id, different publisher URL): keep the original row, just mark it seen.
        """
        if not urls:
            return 0
        now = _now()
        touched = 0
        with self._conn:
            for chunk in _chunked(sorted(set(urls))):
                placeholders = ",".join("?" * len(chunk))
                touched += self._conn.execute(
                    f"UPDATE jobs SET last_seen_at = ? WHERE url IN ({placeholders})",
                    (now, *chunk),
                ).rowcount
                self._conn.execute(
                    f"""
                    UPDATE jobs SET status = 'open', closed_at = NULL
                    WHERE status = 'closed' AND url IN ({placeholders})
                    """,
                    chunk,
                )
        return touched

    def known_urls(self, urls: set[str]) -> set[str]:
        """Which of these URLs are already in the table (any board)."""
        found: set[str] = set()
        for chunk in _chunked(sorted(urls)):
            placeholders = ",".join("?" * len(chunk))
            found.update(
                row[0]
                for row in self._conn.execute(
                    f"SELECT url FROM jobs WHERE url IN ({placeholders})", chunk
                )
            )
        return found

    def known_external_ids(self, ids: set[str]) -> dict[str, str]:
        """Map provider id -> stored url, for postings we already have."""
        found: dict[str, str] = {}
        for chunk in _chunked(sorted(ids)):
            placeholders = ",".join("?" * len(chunk))
            found.update(
                (row[0], row[1])
                for row in self._conn.execute(
                    f"SELECT external_id, url FROM jobs "
                    f"WHERE external_id IN ({placeholders})",
                    chunk,
                )
            )
        return found

    def embedding_hashes(self, board: Board) -> dict[str, str]:
        """Return the embedding-text hash already stored for each job on a board."""
        rows = self._conn.execute(
            "SELECT url, embedding_text_hash FROM jobs WHERE board_slug = ?",
            (board.board_slug,),
        ).fetchall()
        return {row["url"]: row["embedding_text_hash"] for row in rows if row["embedding_text_hash"]}

    def open_postings(self, company_slugs: set[str]) -> list[dict]:
        """Open jobs of these companies, for the aggregator duplicate check."""
        if not company_slugs:
            return []
        found: list[dict] = []
        for chunk in _chunked(sorted(company_slugs)):
            placeholders = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                f"""
                SELECT url, company_slug, title, locations_json, monitor_type
                FROM jobs WHERE status = 'open' AND company_slug IN ({placeholders})
                """,
                chunk,
            )
            for row in rows:
                found.append(
                    {
                        "url": row["url"],
                        "company_slug": row["company_slug"],
                        "title": row["title"],
                        "locations": _json_list(row["locations_json"]),
                        "monitor_type": row["monitor_type"],
                    }
                )
        return found

    # ---- budget / housekeeping ------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row is not None else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
            )

    def count_jobs(self, *, monitor_type: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE monitor_type = ?", (monitor_type,)
        ).fetchone()
        return int(row[0])

    def database_bytes(self) -> int:
        return self.path.stat().st_size if self.path.exists() else 0

    # ---- reading (used by the CLI) -------------------------------------------

    def stats(self) -> dict[str, int | str]:
        row = self._conn.execute(
            """
            SELECT
                COALESCE(SUM(status = 'open'), 0)   AS open_jobs,
                COALESCE(SUM(status = 'closed'), 0) AS closed_jobs,
                COUNT(DISTINCT company_slug)        AS companies_with_jobs,
                COUNT(DISTINCT board_slug)          AS boards
            FROM jobs
            """
        ).fetchone()
        companies = self._conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        return {
            "db": str(self.path),
            "open_jobs": int(row["open_jobs"]),
            "closed_jobs": int(row["closed_jobs"]),
            "companies_with_jobs": int(row["companies_with_jobs"]),
            "boards": int(row["boards"]),
            "companies_loaded": int(companies),
        }

    def sample(self, n: int = 5) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT c.name AS company, j.title, j.seniority, j.occupation,
                   j.technologies_json, j.locations_json, j.url
            FROM jobs j LEFT JOIN companies c ON c.slug = j.company_slug
            WHERE j.status = 'open'
            ORDER BY j.last_seen_at DESC
            LIMIT ?
            """,
            (n,),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
