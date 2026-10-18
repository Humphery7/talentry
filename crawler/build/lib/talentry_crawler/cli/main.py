"""The `talentry-crawl` command. The only place a human starts the crawler."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from talentry_crawler.ats import REGISTRY
from talentry_crawler.pipeline import BoardRunResult, crawl_boards
from talentry_crawler.storage import JobStore


def _build_parser() -> argparse.ArgumentParser:
    supported = ",".join(sorted(REGISTRY))
    parser = argparse.ArgumentParser(
        prog="talentry-crawl",
        description="Crawl ATS job boards into the local jobs database.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="Crawl boards from data/boards.csv")
    run.add_argument("--ats", default=supported, help=f"Comma-separated ATS types (default: {supported})")
    run.add_argument("--company", help="Only crawl this company_slug")
    run.add_argument("--limit", type=int, help="Max number of boards to crawl")
    run.add_argument("--db", type=Path, help="SQLite path (default: output/jobs.db)")
    run.add_argument("--concurrency", type=int, default=5, help="Boards fetched at once (default: 5)")

    stats = commands.add_parser("stats", help="Show counts in the jobs database")
    stats.add_argument("--db", type=Path)

    sample = commands.add_parser("sample", help="Print some recent open jobs")
    sample.add_argument("--db", type=Path)
    sample.add_argument("--n", type=int, default=5)

    return parser


def _print_run_summary(results: list[BoardRunResult]) -> None:
    ok = [r for r in results if r.error is None]
    failed = [r for r in results if r.error is not None]
    print(
        f"boards={len(results)} ok={len(ok)} failed={len(failed)} "
        f"jobs={sum(r.job_count for r in ok)} "
        f"new={sum(r.inserted for r in ok)} "
        f"refreshed={sum(r.updated for r in ok)} "
        f"closed={sum(r.closed for r in ok)}"
    )
    for r in results:
        if r.error:
            print(f"  FAIL {r.board_slug} ({r.monitor_type}): {r.error}", file=sys.stderr)
        else:
            print(f"  OK   {r.board_slug}: {r.job_count} jobs (new {r.inserted}, closed {r.closed})")


def _run(args: argparse.Namespace) -> int:
    ats = [name.strip() for name in args.ats.split(",") if name.strip()]
    results = asyncio.run(
        crawl_boards(
            ats=ats,
            company=args.company,
            limit=args.limit,
            db_path=args.db,
            concurrency=args.concurrency,
        )
    )
    _print_run_summary(results)
    everything_failed = bool(results) and all(r.error for r in results)
    return 1 if everything_failed else 0


def _show(args: argparse.Namespace) -> int:
    store = JobStore(args.db)
    try:
        data = store.stats() if args.command == "stats" else store.sample(args.n)
    finally:
        store.close()
    print(json.dumps(data, indent=2))
    return 0


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    try:
        exit_code = _run(args) if args.command == "run" else _show(args)
    except (ValueError, RuntimeError) as exc:  # bad --ats value, or an old jobs.db
        print(f"error: {exc}", file=sys.stderr)
        exit_code = 2
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
