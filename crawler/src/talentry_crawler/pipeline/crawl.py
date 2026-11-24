"""The crawl, start to finish. This file only decides the ORDER of things;
the details live in the layer each step calls.

    config      load companies, boards and label dictionaries from data/*.csv
    ats         fetch one board's jobs from Greenhouse / Ashby / Lever
    labeling    add seniority / occupation / technologies to each job
    filtering   keep only tech / data / engineering jobs
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
from talentry_crawler.models import MONITORS_WITHOUT_CLOSE, Board, Job
from talentry_crawler.pipeline.duplicate_guard import EmployerIndex, drop_employer_copies
from talentry_crawler.pipeline.jsearch_budget import plan_jsearch, record_jsearch_spend
from talentry_crawler.pipeline.tech_filter import is_tech_job
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
    duplicates: int = 0  # aggregator copies of a job an employer board already has
    error: str | None = None
    note: str | None = None  # why a whole source was skipped (not a failure)


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
    tech_only: bool = True,
    jsearch_now: bool = False,
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
        # Resolves an aggregator posting's employer name to a company we crawl.
        employer_index = EmployerIndex(companies)
        labeler = Labeler(load_label_dictionaries())
        slots = asyncio.Semaphore(concurrency)  # limits how many boards are fetched at once
        # JSearch credits are the scarce resource, and two searches can return
        # the same posting. Running its boards one at a time keeps the dedupe
        # check and the insert in step, and avoids hammering the API.
        jsearch_slots = asyncio.Semaphore(1)

        notes: list[BoardRunResult] = []
        jsearch_boards = [b for b in boards if b.monitor_type == "jsearch"]
        planned_requests = 0
        if jsearch_boards:
            plan = plan_jsearch(store, jsearch_boards, force=jsearch_now)
            planned_requests = plan.requests
            if plan.note:
                notes.append(
                    BoardRunResult("jsearch", "jsearch", "jsearch", note=plan.note)
                )
            boards = [b for b in boards if b.monitor_type != "jsearch"] + plan.boards

        # 3. Crawl every board (up to `concurrency` at once).
        # as_completed (not gather) so we can report progress as each finishes.
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "talentry-crawler/0.1 (+local-dev)"},
        ) as client:

            async def run(board: Board) -> BoardRunResult:
                gate = (
                    jsearch_slots
                    if board.monitor_type in MONITORS_WITHOUT_CLOSE
                    else slots
                )
                async with gate:
                    return await crawl_one_board(
                        board,
                        client,
                        labeler,
                        store,
                        company_name=company_names.get(board.company_slug),
                        embedder=embedder,
                        tech_only=tech_only,
                        employer_index=employer_index,
                    )

            done = 0

            async def run_all(subset: list[Board]) -> list[BoardRunResult]:
                nonlocal done
                tasks = [asyncio.create_task(run(b)) for b in subset]
                finished: list[BoardRunResult] = []
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    finished.append(result)
                    done += 1
                    if on_progress is not None:
                        on_progress(result, done, len(boards))
                return finished

            employer_boards = [
                b for b in boards if b.monitor_type not in MONITORS_WITHOUT_CLOSE
            ]
            aggregator_boards = [
                b for b in boards if b.monitor_type in MONITORS_WITHOUT_CLOSE
            ]
            results = await run_all(employer_boards)
            # Employer boards first, on purpose: the aggregator guard compares
            # against what the employer's own board just stored today.
            results += await run_all(aggregator_boards)
            if jsearch_boards:
                record_jsearch_spend(store, planned_requests)
            return notes + results
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
    tech_only: bool = True,
    employer_index: EmployerIndex | None = None,
) -> BoardRunResult:
    """fetch -> label -> filter -> dedupe -> embed -> save, for one board. Errors are reported, not raised."""
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
        if tech_only:
            jobs = [job for job in jobs if is_tech_job(job)]
        found = len(jobs)
        jobs, refreshed = drop_already_stored(jobs, store)
        duplicates = 0
        if employer_index is not None and board.monitor_type in MONITORS_WITHOUT_CLOSE:
            # Only an aggregator row can be a copy of an employer's own posting.
            jobs, duplicates = drop_employer_copies(jobs, store, employer_index)
        await embed_jobs(board, jobs, company_name, store, embedder or embed_texts)
        inserted, updated, closed = store.save_board_jobs(board, jobs)
    except Exception as exc:  # noqa: BLE001 — one bad board must not stop the others
        # Nothing is saved or closed when the fetch fails, so a flaky site never wipes its jobs.
        result.error = f"{type(exc).__name__}: {exc}"
        return result

    result.job_count = found
    result.inserted = inserted
    result.updated = updated + refreshed
    result.closed = closed
    result.duplicates = duplicates
    return result


def drop_already_stored(jobs: list[Job], store: JobStore) -> tuple[list[Job], int]:
    """Drop postings we already have, returning the new ones and how many were refreshed.

    Only sources that report their own posting id (JSearch's `external_id`)
    take this path. A posting can arrive several times in one day because five
    searches match it, often under different publisher URLs; the stored row is
    kept as it is and merely marked as seen. The URL check also stops a posting
    we already crawl from the employer's own career page from being rewritten
    under an aggregator board.
    """
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        if job.external_id:
            if job.external_id in seen_ids or job.url in seen_urls:
                continue
            seen_ids.add(job.external_id)
        elif job.url in seen_urls:
            continue
        seen_urls.add(job.url)
        unique.append(job)

    if not seen_ids:
        return unique, 0

    known_urls = store.known_urls(seen_urls)
    known_ids = store.known_external_ids(seen_ids)
    fresh: list[Job] = []
    refresh: list[str] = []
    for job in unique:
        if job.url in known_urls:
            refresh.append(job.url)
        elif job.external_id and job.external_id in known_ids:
            refresh.append(known_ids[job.external_id])
        else:
            fresh.append(job)
    return fresh, store.touch_urls(refresh)


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
            company_name=job.company_name or company_name,
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
