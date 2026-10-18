"""The crawl, start to finish. This file only decides the ORDER of things;
the details live in the layer each step calls.

    config    load companies, boards and label dictionaries from data/*.csv
    ats       fetch one board's jobs from Greenhouse / Ashby / Lever
    labeling  add seniority / occupation / technologies to each job
    storage   save the jobs (and close the ones that disappeared)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx

from talentry_crawler.ats import REGISTRY, get_discoverer
from talentry_crawler.config import load_boards, load_companies, load_label_dictionaries
from talentry_crawler.labeling import Labeler
from talentry_crawler.models import Board
from talentry_crawler.storage import JobStore


@dataclass(slots=True)
class BoardRunResult:
    """What happened to one board. The CLI prints these."""

    board_slug: str
    company_slug: str
    monitor_type: str
    job_count: int = 0  # jobs found on the page
    inserted: int = 0  # new to us
    updated: int = 0  # already known, refreshed
    closed: int = 0  # known before, no longer on the page
    error: str | None = None


async def crawl_boards(
    *,
    ats: list[str] | None = None,
    company: str | None = None,
    limit: int | None = None,
    db_path: Path | str | None = None,
    concurrency: int = 5,
    timeout: float = 30.0,
) -> list[BoardRunResult]:
    """Crawl the selected boards and save what we find. One failing board never stops the rest."""
    ats = ats or sorted(REGISTRY)
    unknown = sorted(set(ats) - set(REGISTRY))
    if unknown:
        raise ValueError(f"No adapter for {unknown}. Supported: {sorted(REGISTRY)}")

    # 1. What to crawl
    boards = load_boards(ats=ats, company=company, limit=limit)
    if not boards:
        return []

    # 2. Where to save, and the tools each board will need
    store = JobStore(db_path)
    try:
        store.save_companies(load_companies())
        labeler = Labeler(load_label_dictionaries())
        slots = asyncio.Semaphore(concurrency)  # limits how many boards are fetched at once

        # 3. Crawl every board (up to `concurrency` at once)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "talentry-crawler/0.1 (+local-dev)"},
        ) as client:

            async def run(board: Board) -> BoardRunResult:
                async with slots:
                    return await crawl_one_board(board, client, labeler, store)

            return list(await asyncio.gather(*(run(b) for b in boards)))
    finally:
        store.close()


async def crawl_one_board(
    board: Board, client: httpx.AsyncClient, labeler: Labeler, store: JobStore
) -> BoardRunResult:
    """fetch -> label -> save, for one board. Errors are reported, not raised."""
    result = BoardRunResult(
        board_slug=board.board_slug,
        company_slug=board.company_slug,
        monitor_type=board.monitor_type,
    )
    try:
        discover = get_discoverer(board.monitor_type)
        jobs = await discover(board, client)
        for job in jobs:
            labeler.label(job)
        inserted, updated, closed = store.save_board_jobs(board, jobs)
    except Exception as exc:  # noqa: BLE001 — one bad board must not stop the others
        # Nothing is saved or closed when the fetch fails, so a flaky site never wipes its jobs.
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.job_count = len(jobs)
    result.inserted, result.updated, result.closed = inserted, updated, closed
    return result
