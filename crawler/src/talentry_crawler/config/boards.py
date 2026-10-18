"""Load data/boards.csv: which career pages to crawl, and which ATS adapter reads each."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from talentry_crawler.models import Board

from .paths import DATA_DIR


def _parse_json_field(raw: str | None) -> dict:
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def load_boards(
    path: Path | None = None,
    *,
    ats: Iterable[str] | None = None,
    company: str | None = None,
    limit: int | None = None,
) -> list[Board]:
    """Load boards.csv, optionally keeping only some ATS types / one company / the first N."""
    csv_path = path or (DATA_DIR / "boards.csv")
    allowed = {a.strip().lower() for a in ats} if ats else None

    boards: list[Board] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            monitor_type = (row.get("monitor_type") or "").strip().lower()
            if allowed is not None and monitor_type not in allowed:
                continue
            company_slug = (row.get("company_slug") or "").strip()
            if company and company_slug != company:
                continue

            boards.append(
                Board(
                    company_slug=company_slug,
                    board_slug=(row.get("board_slug") or "").strip(),
                    board_url=(row.get("board_url") or "").strip(),
                    monitor_type=monitor_type,
                    monitor_config=_parse_json_field(row.get("monitor_config")),
                    scraper_type=(row.get("scraper_type") or "").strip() or None,
                    scraper_config=_parse_json_field(row.get("scraper_config")),
                )
            )
            if limit is not None and len(boards) >= limit:
                break

    return boards
