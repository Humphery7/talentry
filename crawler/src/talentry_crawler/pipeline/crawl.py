"""The crawl, start to finish. This file only decides the ORDER of things;
the details live in the layer each step calls.

    config      load companies, boards and label dictionaries from data/*.csv
    ats         fetch one board's jobs from Greenhouse / Ashby / Lever
    labeling    add seniority / occupation / technologies to each job
    embeddings  build the job text and add its vector
    storage     save the jobs (and close the ones that disappeared)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from talentry_crawler.ats import REGISTRY, get_discoverer
from talentry_crawler.config import load_boards, load_companies, load_label_dictionaries
from talentry_crawler.labeling import Labeler
from talentry_crawler.models import Board, Job
from talentry_crawler.storage import JobStore
from talentry_embeddings import build_job_text, embed_texts, text_hash

Embedder = Callable[[list[str]], list[list[float]]]


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
    on_progress: Callable[[BoardRunResult, int, int], None] | None = None,
    embedder: Embedder | None = None,
) -> list[BoardRunResult]:
    """Crawl the selected boards and save what we find. One failing board never stops the rest.

    Calls `on_progress(result, done, total)` as each board finishes, so the CLI
    can show live output instead of going silent until the end.
    """
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
        companies = load_companies()
        store.save_companies(companies)
        company_names = {company.slug: company.name for company in companies}
        labeler = Labeler(load_label_dictionaries())
        slots = asyncio.Semaphore(concurrency)  # limits how many boards are fetched at once

        # 3. Crawl every board (up to `concurrency` at once).
        # as_completed (not gather) so we can report progress as each finishes.
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "talentry-crawler/0.1 (+local-dev)"},
        ) as client:

            async def run(index: int, board: Board) -> tuple[int, BoardRunResult]:
                async with slots:
                    return index, await crawl_one_board(
                        board,
                        client,
                        labeler,
                        store,
                        company_name=company_names.get(board.company_slug),
                        embedder=embedder,
                    )

            tasks = [asyncio.create_task(run(i, b)) for i, b in enumerate(boards)]
            ordered: list[BoardRunResult | None] = [None] * len(boards)
            done = 0
            for coro in asyncio.as_completed(tasks):
                index, result = await coro
                ordered[index] = result
                done += 1
                if on_progress is not None:
                    on_progress(result, done, len(boards))
            return [r for r in ordered if r is not None]
    finally:
        store.close()


async def crawl_one_board(
    board: Board,
    client: httpx.AsyncClient,
    labeler: Labeler,
    store: JobStore,
    *,
    company_name: str | None = None,
    embedder: Embedder | None = None,
) -> BoardRunResult:
    """fetch -> label -> embed -> save, for one board. Errors are reported, not raised."""
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
        await embed_jobs(board, jobs, company_name, store, embedder or embed_texts)
        inserted, updated, closed = store.save_board_jobs(board, jobs)
    except Exception as exc:  # noqa: BLE001 — one bad board must not stop the others
        # Nothing is saved or closed when the fetch fails, so a flaky site never wipes its jobs.
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.job_count = len(jobs)
    result.inserted, result.updated, result.closed = inserted, updated, closed
    return result


async def embed_jobs(
    board: Board,
    jobs: list[Job],
    company_name: str | None,
    store: JobStore,
    embedder: Embedder,
) -> None:
    """Fill each job's vector, skipping jobs whose embedding text is unchanged."""
    existing = store.embedding_hashes(board)
    pending: list[tuple[Job, str]] = []

    for job in jobs:
        text = build_job_text(
            title=job.title,
            description=job.description,
            company_name=company_name,
            locations=job.locations,
            employment_type=job.employment_type,
            workplace_type=job.workplace_type,
            seniority=job.seniority,
            occupation=job.occupation,
            technologies=job.technologies,
        )
        digest = text_hash(text)
        job.embedding_text_hash = digest
        if text and existing.get(job.url) != digest:
            pending.append((job, text))

    if not pending:
        return

    vectors = await asyncio.to_thread(embedder, [text for _, text in pending])
    if len(vectors) != len(pending):
        raise RuntimeError(
            f"Embedding model returned {len(vectors)} vectors for {len(pending)} jobs"
        )

    for (job, _), vector in zip(pending, vectors, strict=True):
        job.embedding = vector
