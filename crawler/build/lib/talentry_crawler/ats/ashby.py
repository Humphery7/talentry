"""Ashby — GET https://api.ashbyhq.com/posting-api/job-board/{token}"""

from __future__ import annotations

import re

import httpx

from talentry_crawler.models import Board, Job

_IGNORE_TOKENS = frozenset({"api", "js", "css", "assets", "posting-api"})


def token_from_url(board_url: str) -> str | None:
    match = re.search(r"jobs\.ashbyhq\.com/([\w-]+)", board_url)
    if match and match.group(1) not in _IGNORE_TOKENS:
        return match.group(1)
    return None


def _api_url(token: str) -> str:
    return f"https://api.ashbyhq.com/posting-api/job-board/{token}"


def _parse_locations(raw: dict) -> list[str] | None:
    locations: list[str] = []
    seen: set[str] = set()

    location = raw.get("location")
    if isinstance(location, str) and location:
        locations.append(location)
        seen.add(location)

    for loc in raw.get("secondaryLocations") or []:
        name = loc if isinstance(loc, str) else (loc.get("location") if isinstance(loc, dict) else "")
        if name and name not in seen:
            locations.append(name)
            seen.add(name)

    if not locations:
        address = raw.get("address")
        if isinstance(address, dict):
            parts = [
                p
                for p in (address.get("city"), address.get("region"), address.get("country"))
                if p
            ]
            if parts:
                locations.append(", ".join(parts))

    return locations or None


def _parse_job(raw: dict) -> Job | None:
    url = raw.get("jobUrl")
    if not url:
        return None

    metadata: dict = {}
    if raw.get("department"):
        metadata["department"] = raw["department"]
    if raw.get("team"):
        metadata["team"] = raw["team"]
    if raw.get("id"):
        metadata["id"] = raw["id"]

    return Job(
        url=url,
        title=raw.get("title") if isinstance(raw.get("title"), str) else None,
        description=raw.get("descriptionHtml") or raw.get("descriptionPlain"),
        locations=_parse_locations(raw),
        employment_type=raw.get("employmentType")
        if isinstance(raw.get("employmentType"), str)
        else None,
        workplace_type=raw.get("workplaceType")
        if isinstance(raw.get("workplaceType"), str)
        else None,
        date_posted=raw.get("publishedAt") if isinstance(raw.get("publishedAt"), str) else None,
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    token = board.monitor_config.get("token") or token_from_url(board.board_url)
    if not token:
        raise ValueError(
            f"Cannot derive Ashby token from {board.board_url!r} "
            "and no token in monitor_config"
        )

    response = await client.get(_api_url(token), params={"includeCompensation": "true"})
    if response.status_code == 404:
        raise LookupError(f"Ashby board token {token!r} returned 404 (board gone)")
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Ashby response must be a JSON object")
    raw_jobs = data.get("jobs")
    if not isinstance(raw_jobs, list):
        raise ValueError("Ashby response must contain a jobs list")

    jobs: list[Job] = []
    for index, raw in enumerate(raw_jobs):
        if not isinstance(raw, dict):
            raise ValueError(f"Ashby job at index {index} must be an object")
        parsed = _parse_job(raw)
        if parsed is None:
            continue
        jobs.append(parsed)
    return jobs
