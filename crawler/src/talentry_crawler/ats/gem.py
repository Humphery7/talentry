"""Gem — GET https://api.gem.com/job_board/v0/{slug}/job_posts/"""

from __future__ import annotations

import re

import httpx

from talentry_crawler.models import Board, Job

_SLUG_RE = re.compile(r"jobs\.gem\.com/([\w-]+)")
_IGNORE_SLUGS = frozenset({"api", "www", "app", "docs", "help", "support"})


def slug_from_url(board_url: str) -> str | None:
    match = _SLUG_RE.search(board_url)
    if match and match.group(1) not in _IGNORE_SLUGS:
        return match.group(1)
    return None


def _api_url(slug: str) -> str:
    return f"https://api.gem.com/job_board/v0/{slug}/job_posts/"


def _parse_locations(post: dict) -> list[str] | None:
    locations: list[str] = []
    seen: set[str] = set()

    for office in post.get("offices") or []:
        if not isinstance(office, dict):
            continue
        location = office.get("location")
        name = location.get("name") if isinstance(location, dict) else office.get("name")
        if isinstance(name, str) and name and name not in seen:
            locations.append(name)
            seen.add(name)

    if not locations:
        location = post.get("location")
        if isinstance(location, dict) and location.get("name"):
            locations.append(location["name"])
        elif isinstance(location, str) and location:
            locations.append(location)

    return locations or None


def _parse_job(post: dict) -> Job | None:
    url = post.get("absolute_url")
    if not isinstance(url, str) or not url:
        return None

    metadata: dict = {}
    departments = [
        department["name"]
        for department in post.get("departments") or []
        if isinstance(department, dict) and department.get("name")
    ]
    if departments:
        metadata["department"] = ", ".join(departments)

    return Job(
        url=url,
        title=post.get("title") if isinstance(post.get("title"), str) else None,
        description=post.get("content") if isinstance(post.get("content"), str) else None,
        locations=_parse_locations(post),
        employment_type=post.get("employment_type") or None,
        workplace_type=post.get("location_type") or None,
        date_posted=post.get("first_published_at"),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("token") or board.monitor_config.get("slug")
    slug = slug or slug_from_url(board.board_url)
    if not slug:
        raise ValueError(
            f"Cannot derive Gem slug from {board.board_url!r} "
            "and no token/slug in monitor_config"
        )

    response = await client.get(_api_url(slug), follow_redirects=True)
    if response.status_code == 404:
        raise LookupError(f"Gem board {slug!r} returned 404 (board gone)")
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, list):
        raise ValueError("Gem response must be a JSON array")

    jobs: list[Job] = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_job(raw)
        if parsed is not None:
            jobs.append(parsed)
    return jobs
