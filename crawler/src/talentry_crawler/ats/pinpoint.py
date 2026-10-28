"""Pinpoint — GET https://{slug}.pinpointhq.com/postings.json"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_DOMAIN_RE = re.compile(r"^([\w-]+)\.pinpointhq\.com$")
_IGNORE_SLUGS = frozenset({"api", "www", "app", "docs", "help", "support", "status"})
_SALARY_UNITS = {
    "annual": "year",
    "annum": "year",
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


def _api_url(slug: str) -> str:
    return f"https://{slug}.pinpointhq.com/postings.json"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _build_description(posting: dict) -> str | None:
    parts: list[str] = []
    for key, header_key in (
        ("description", None),
        ("key_responsibilities", "key_responsibilities_header"),
        ("skills_knowledge_expertise", "skills_knowledge_expertise_header"),
        ("benefits", "benefits_header"),
    ):
        text = posting.get(key)
        if not isinstance(text, str) or not text:
            continue
        header = posting.get(header_key)
        parts.append(f"<h3>{header}</h3>\n{text}" if isinstance(header, str) and header else text)
    return "\n".join(parts) or None


def _parse_locations(posting: dict) -> list[str] | None:
    location = posting.get("location")
    if not isinstance(location, dict):
        return None

    name = _clean_text(location.get("name"))
    if name:
        return [name]

    parts = [part for part in (location.get("city"), location.get("province")) if part]
    return [", ".join(parts)] if parts else None


def _parse_salary(posting: dict) -> dict | None:
    minimum = posting.get("compensation_minimum")
    maximum = posting.get("compensation_maximum")
    if (minimum is None and maximum is None) or not posting.get("compensation_visible", True):
        return None

    frequency = posting.get("compensation_frequency")
    unit = _SALARY_UNITS.get(str(frequency).lower()) if frequency else "year"
    return {
        "currency": posting.get("compensation_currency"),
        "min": minimum,
        "max": maximum,
        "unit": unit or "year",
    }


def _parse_job(posting: dict) -> Job | None:
    url = posting.get("url")
    if not isinstance(url, str) or not url:
        return None

    metadata: dict = {}
    job = posting.get("job")
    if isinstance(job, dict):
        department = job.get("department")
        if isinstance(department, dict) and department.get("name"):
            metadata["department"] = department["name"]
        division = job.get("division")
        if isinstance(division, dict) and division.get("name"):
            metadata["division"] = division["name"]
        if job.get("requisition_id"):
            metadata["requisition_id"] = job["requisition_id"]

    return Job(
        url=url,
        title=_clean_text(posting.get("title")),
        description=_build_description(posting),
        locations=_parse_locations(posting),
        employment_type=posting.get("employment_type")
        or posting.get("employment_type_text")
        or None,
        workplace_type=posting.get("workplace_type") or None,
        date_posted=posting.get("created_at") or posting.get("updated_at"),
        salary=_parse_salary(posting),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not slug:
        raise ValueError(
            f"Cannot derive Pinpoint slug from {board.board_url!r} "
            "and no slug in monitor_config"
        )

    response = await client.get(_api_url(slug), follow_redirects=True)
    if response.status_code == 404:
        raise LookupError(f"Pinpoint board {slug!r} returned 404 (board gone)")
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Pinpoint response must be a JSON object")
    raw_jobs = data.get("data")
    if not isinstance(raw_jobs, list):
        raise ValueError("Pinpoint response must contain a data list")

    jobs: list[Job] = []
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_job(raw)
        if parsed is not None:
            jobs.append(parsed)
    return jobs
