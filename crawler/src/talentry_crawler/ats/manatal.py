"""Manatal — GET https://www.careers-page.com/api/v1.0/c/{slug}/jobs/"""

from __future__ import annotations

import re

import httpx

from talentry_crawler.models import Board, Job

PAGE_SIZE = 50
_FRONTEND_BASE = "https://www.careers-page.com"
_SLUG_RE = re.compile(r"(?:www\.)?careers-page\.com/([\w-]+)(?:[/#?]|$)", re.IGNORECASE)
_IGNORE_SLUGS = frozenset({"api", "assets", "job", "jobs", "login", "static", "www"})


def slug_from_url(board_url: str) -> str | None:
    match = _SLUG_RE.search(board_url)
    if not match:
        return None
    slug = match.group(1).lower()
    return None if slug in _IGNORE_SLUGS else slug


def _api_url(slug: str) -> str:
    return f"{_FRONTEND_BASE}/api/v1.0/c/{slug}/jobs/"


def _parse_locations(post: dict) -> list[str] | None:
    display = post.get("location_display")
    if isinstance(display, str) and display.strip():
        return [display.strip()]

    parts = [post.get("city"), post.get("state"), post.get("country")]
    text = ", ".join(str(part).strip() for part in parts if str(part or "").strip())
    return [text] if text else None


def _parse_job(post: dict, slug: str) -> Job | None:
    job_hash = post.get("hash")
    if not isinstance(job_hash, str) or not job_hash:
        return None

    metadata = {"id": post["id"]} if post.get("id") is not None else None
    return Job(
        url=f"{_FRONTEND_BASE}/{slug}/job/{job_hash}",
        title=post.get("position_name")
        if isinstance(post.get("position_name"), str)
        else None,
        description=post.get("description")
        if isinstance(post.get("description"), str)
        else None,
        locations=_parse_locations(post),
        metadata=metadata,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not slug:
        raise ValueError(
            f"Cannot derive Manatal slug from {board.board_url!r} "
            "and no slug in monitor_config"
        )

    jobs: list[Job] = []
    page = 1
    while True:
        response = await client.get(
            _api_url(slug),
            params={
                "page_size": PAGE_SIZE,
                "page": page,
                "ordering": "-is_pinned_in_career_page,-last_published_at",
            },
            follow_redirects=True,
        )
        if response.status_code == 404 and page == 1:
            raise LookupError(f"Manatal board {slug!r} returned 404 (board gone)")
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError("Manatal response must contain a results list")

        for raw in data["results"]:
            if not isinstance(raw, dict):
                continue
            parsed = _parse_job(raw, slug)
            if parsed is not None:
                jobs.append(parsed)

        if not data.get("next"):
            break
        page += 1

    return jobs
