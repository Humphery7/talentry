"""Recruitee — GET https://{slug}.recruitee.com/api/offers"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_DOMAIN_RE = re.compile(r"^([\w-]+)\.recruitee\.com$")
_IGNORE_SLUGS = frozenset({"api", "www", "app", "docs", "help", "support", "status"})
_SALARY_UNITS = {
    "annual": "year",
    "annually": "year",
    "yearly": "year",
    "monthly": "month",
    "weekly": "week",
    "daily": "day",
    "hourly": "hour",
}


def slug_from_url(board_url: str) -> str | None:
    host = (urlparse(board_url).hostname or "").lower()
    match = _DOMAIN_RE.match(host)
    if match and match.group(1) not in _IGNORE_SLUGS:
        return match.group(1)
    return None


def _api_base(board: Board) -> str | None:
    configured = board.monitor_config.get("api_base")
    if isinstance(configured, str) and configured:
        return configured.rstrip("/")

    slug = board.monitor_config.get("slug") or board.monitor_config.get("token")
    if not slug:
        slug = slug_from_url(board.board_url)
    if slug:
        return f"https://{slug}.recruitee.com"

    host = urlparse(board.board_url).hostname
    return f"https://{host}" if host else None


def _parse_locations(offer: dict) -> list[str] | None:
    locations: list[str] = []
    seen: set[str] = set()

    for location in offer.get("locations") or []:
        if not isinstance(location, dict):
            continue
        parts = [part for part in (location.get("city"), location.get("country")) if part]
        name = ", ".join(parts)
        if name and name not in seen:
            locations.append(name)
            seen.add(name)

    flat = offer.get("location")
    if not locations and isinstance(flat, str) and flat:
        locations.append(flat)

    return locations or None


def _parse_salary(offer: dict) -> dict | None:
    salary = offer.get("salary")
    if not isinstance(salary, dict):
        return None
    minimum = salary.get("min")
    maximum = salary.get("max")
    if minimum is None and maximum is None:
        return None

    period = salary.get("period")
    unit = _SALARY_UNITS.get(str(period).lower()) if period else "year"
    return {
        "currency": salary.get("currency"),
        "min": minimum,
        "max": maximum,
        "unit": unit or "year",
    }


def _parse_job(offer: dict) -> Job | None:
    url = offer.get("careers_url")
    if not isinstance(url, str) or not url:
        return None

    parts = [part for part in (offer.get("description"), offer.get("requirements")) if part]
    metadata: dict = {}
    if offer.get("department"):
        metadata["department"] = offer["department"]
    if offer.get("category_code"):
        metadata["category"] = offer["category_code"]
    if offer.get("tags"):
        metadata["tags"] = offer["tags"]
    if offer.get("id"):
        metadata["id"] = offer["id"]

    workplace_type = None
    if offer.get("remote"):
        workplace_type = "remote"
    elif offer.get("hybrid"):
        workplace_type = "hybrid"
    elif offer.get("on_site"):
        workplace_type = "onsite"

    return Job(
        url=url,
        title=offer.get("title") if isinstance(offer.get("title"), str) else None,
        description="\n".join(parts) if parts else None,
        locations=_parse_locations(offer),
        employment_type=offer.get("employment_type_code") or None,
        workplace_type=workplace_type,
        date_posted=offer.get("published_at"),
        salary=_parse_salary(offer),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    api_base = _api_base(board)
    if not api_base:
        raise ValueError(
            f"Cannot derive Recruitee API base from {board.board_url!r} "
            "and no slug/api_base in monitor_config"
        )

    response = await client.get(f"{api_base}/api/offers", follow_redirects=True)
    if response.status_code == 404:
        raise LookupError(f"Recruitee board {api_base!r} returned 404 (board gone)")
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Recruitee response must be a JSON object")
    raw_jobs = data.get("offers")
    if not isinstance(raw_jobs, list):
        raise ValueError("Recruitee response must contain an offers list")

    jobs: list[Job] = []
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_job(raw)
        if parsed is not None:
            jobs.append(parsed)
    return jobs
