"""How much of the month's JSearch quota may be spent right now.

JSearch charges one request credit per page of up to 10 jobs, and the free plan
(200 requests/month) is a hard stop rather than a bill. Requests are the scarce
thing here, not bytes: even a full 180 requests/month is only ~15 MB of job
rows, so there is no per-source storage cap. What this module protects is

  * the API quota — JSearch runs once per ISO week even though the whole
    crawler runs daily, and never past JSEARCH_MONTHLY_REQUESTS;
  * the 1 GB database — it refuses to call the API when the database is close
    to DB_STORAGE_LIMIT_MB, or when JSearch rows pass JSEARCH_MAX_ROWS.

Both counters live in the `meta` table, so a restart or a fresh GitHub Actions
runner does not forget what was already spent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from talentry_crawler.models import Board

DEFAULT_MONTHLY_REQUESTS = 180  # 200/month plan, 20 kept back for manual runs
DEFAULT_MAX_ROWS = 5_000  # ~40 MB of JSearch rows: a runaway guard, not a budget
DEFAULT_STORAGE_LIMIT_MB = 1_000  # Neon free plan
STORAGE_BRAKE = 0.9  # stop adding JSearch rows at 90% of the limit


@dataclass(slots=True)
class JSearchPlan:
    """Which JSearch boards to run now, and why (or why not)."""

    boards: list[Board] = field(default_factory=list)
    requests: int = 0
    note: str | None = None


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _pages(board: Board) -> int:
    try:
        pages = int(board.monitor_config.get("num_pages", 1))
    except (TypeError, ValueError):
        pages = 1
    return max(1, pages)


def _used_this_month(store, month: str) -> int:
    raw = store.get_meta(f"jsearch:requests:{month}")
    try:
        return max(0, int(raw or 0))
    except ValueError:
        return 0


def plan_jsearch(
    store,
    boards: list[Board],
    *,
    force: bool = False,
    now: datetime | None = None,
) -> JSearchPlan:
    """Pick the JSearch queries to spend credits on in this run.

    `force` skips the once-a-week rule (for `talentry-crawl run --jsearch-now`)
    but still obeys the monthly budget and the storage guards.
    """
    if not boards:
        return JSearchPlan()

    now = now or datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    year, week, _ = now.isocalendar()
    week_key = f"{year}-W{week:02d}"

    if not os.environ.get("JSEARCH_API_KEY", "").strip().strip("\"'"):
        return JSearchPlan(note="JSEARCH_API_KEY is not set — skipping JSearch")

    monthly = _int_env("JSEARCH_MONTHLY_REQUESTS", DEFAULT_MONTHLY_REQUESTS)
    if monthly <= 0:
        return JSearchPlan(note="JSEARCH_MONTHLY_REQUESTS is 0 — JSearch is off")
    weekly = min(_int_env("JSEARCH_WEEKLY_REQUESTS", max(1, monthly // 4)), monthly)

    if not force and store.get_meta(f"jsearch:week:{week_key}"):
        return JSearchPlan(note=f"already ran this week ({week_key})")

    used = _used_this_month(store, month)
    if used >= monthly:
        return JSearchPlan(
            note=f"monthly request budget spent ({used}/{monthly} for {month})"
        )

    max_rows = _int_env("JSEARCH_MAX_ROWS", DEFAULT_MAX_ROWS)
    rows = store.count_jobs(monitor_type="jsearch")
    if max_rows and rows >= max_rows:
        return JSearchPlan(note=f"JSearch row ceiling reached ({rows}/{max_rows})")

    limit_mb = _int_env("DB_STORAGE_LIMIT_MB", DEFAULT_STORAGE_LIMIT_MB)
    size = store.database_bytes() or 0
    brake = int(limit_mb * STORAGE_BRAKE)
    if limit_mb and size >= brake * 1024 * 1024:
        return JSearchPlan(
            note=(
                f"database is at {size / 1024 / 1024:.0f} MB "
                f"(JSearch pauses at {brake} MB of {limit_mb} MB)"
            )
        )

    allowance = min(weekly, monthly - used)
    if allowance <= 0:
        return JSearchPlan(note=f"weekly request budget spent ({used}/{monthly})")

    # Rotate through the query list so a short weekly allowance still covers
    # every query over the following weeks instead of starving the tail.
    offset = ((week - 1) * max(weekly, 1)) % len(boards)
    chosen: list[Board] = []
    spent = 0
    for step in range(len(boards)):
        board = boards[(offset + step) % len(boards)]
        pages = _pages(board)
        if spent + pages > allowance:
            break
        chosen.append(board)
        spent += pages

    if not chosen:
        return JSearchPlan(note=f"weekly request budget spent ({used}/{monthly})")
    return JSearchPlan(boards=chosen, requests=spent)


def record_jsearch_spend(
    store,
    requests: int,
    *,
    now: datetime | None = None,
) -> None:
    """Book the credits a run used, and mark this ISO week as done."""
    if requests <= 0:
        return
    now = now or datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    year, week, _ = now.isocalendar()
    store.set_meta(
        f"jsearch:requests:{month}", str(_used_this_month(store, month) + requests)
    )
    store.set_meta(f"jsearch:week:{year}-W{week:02d}", now.isoformat())
