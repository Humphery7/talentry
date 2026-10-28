"""Hireology — public careers API with full job descriptions."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_BASE = "https://api.hireology.com/v2/public/careers"
_PAGE_SIZE = 500
_MAX_JOBS = 50_000
_CAREERS_HOST_RE = re.compile(r"^careers\.hireology\.com$")
_CUSTOM_HOST_RE = re.compile(r"^([a-z0-9-]+)\.hireology\.careers$", re.IGNORECASE)
_IGNORE_SLUGS = frozenset({"api", "www", "app", "static", "assets", "js", "css"})


def _slug_from_url(board_url: str) -> str | None:
    parsed = urlparse(board_url)
    host = (parsed.hostname or "").casefold()
    match = _CUSTOM_HOST_RE.match(host)
    if match and match.group(1).casefold() not in _IGNORE_SLUGS:
        return match.group(1)
    if _CAREERS_HOST_RE.match(host):
        first = parsed.path.strip("/").split("/", 1)[0]
        if first and first.casefold() not in _IGNORE_SLUGS:
            return first
    return None


def _locations(raw: object) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    locations: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            parts = [
                value
                for key in ("city", "state")
                if isinstance((value := item.get(key)), str) and value
            ]
            label = ", ".join(parts)
        elif isinstance(item, str):
            label = item
        else:
            label = ""
        if label and label not in locations:
            locations.append(label)
    return locations or None


def _parse_job(raw: dict) -> Job | None:
    if raw.get("status") != "Open":
        return None
    url = raw.get("career_site_url")
    title = raw.get("name")
    if not isinstance(url, str) or not url:
        return None
    if not isinstance(title, str) or not title.strip():
        return None

    metadata: dict[str, object] = {}
    organization = raw.get("organization")
    if isinstance(organization, dict):
        name = organization.get("name")
        if isinstance(name, str) and name:
            metadata["organization"] = name
    job_family = raw.get("job_family")
    if isinstance(job_family, dict):
        name = job_family.get("name")
        if isinstance(name, str) and name:
            metadata["job_family"] = name
    if raw.get("id") is not None:
        metadata["id"] = raw["id"]

    employment_type = raw.get("employment_status")
    date_posted = raw.get("created_at")
    return Job(
        url=url,
        title=title.strip(),
        description=(
            raw.get("job_description")
            if isinstance(raw.get("job_description"), str)
            else None
        ),
        locations=_locations(raw.get("locations")),
        employment_type=employment_type if isinstance(employment_type, str) else None,
        workplace_type="remote" if raw.get("remote") is True else None,
        date_posted=date_posted if isinstance(date_posted, str) else None,
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    metadata = board.monitor_config
    slug = metadata.get("slug") or _slug_from_url(board.board_url)
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"Cannot derive Hireology slug from {board.board_url!r}")

    jobs: list[Job] = []
    seen: set[str] = set()
    page = 1
    while len(jobs) < _MAX_JOBS:
        response = await client.get(
            f"{_BASE}/{slug}",
            params={"page_size": _PAGE_SIZE, "page": page},
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Hireology response is not an object")
        rows = payload.get("data")
        total = payload.get("count")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("Hireology response has invalid job rows")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise ValueError("Hireology response has an invalid count")

        for raw in rows:
            job = _parse_job(raw)
            if job is not None and job.url not in seen:
                seen.add(job.url)
                jobs.append(job)
                if len(jobs) >= _MAX_JOBS:
                    break
        if page * _PAGE_SIZE >= total or len(rows) < _PAGE_SIZE:
            break
        page += 1

    return jobs
