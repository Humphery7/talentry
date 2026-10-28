"""Traffit — GET https://{slug}.traffit.com/public/job_posts/published"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

PAGE_SIZE = 100
_IGNORE_SLUGS = frozenset({"www", "api", "cdn", "cdn3", "app", "help", "knowledge"})
_SALARY_UNITS = {
    "annual": "year",
    "yearly": "year",
    "monthly": "month",
    "weekly": "week",
    "daily": "day",
    "hourly": "hour",
}


def slug_from_url(board_url: str) -> str | None:
    host = (urlparse(board_url).hostname or "").lower()
    if host.endswith(".traffit.com"):
        slug = host.removesuffix(".traffit.com")
        if slug and slug not in _IGNORE_SLUGS:
            return slug
    return None


def _api_url(slug: str) -> str:
    return f"https://{slug}.traffit.com/public/job_posts/published"


def _get_value(values: list[dict], field_id: str) -> str | None:
    for item in values:
        if isinstance(item, dict) and item.get("field_id") == field_id:
            value = item.get("value")
            return value if isinstance(value, str) else None
    return None


def _parse_locations(values: list[dict]) -> list[str] | None:
    raw = _get_value(values, "geolocation")
    if not raw:
        return None
    try:
        geolocation = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(geolocation, dict):
        return None

    locality = geolocation.get("locality")
    if not locality:
        return None
    country = geolocation.get("country")
    return [f"{locality}, {country}" if country else str(locality)]


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_salary(options: dict) -> dict | None:
    minimum = _number(options.get("_Salary_MIN"))
    maximum = _number(options.get("_Salary_MAX"))
    currency = options.get("_Salary_Currency")
    if not currency or (minimum is None and maximum is None):
        return None

    rate = options.get("_Salary_Rate")
    unit = _SALARY_UNITS.get(str(rate).lower()) if rate else "month"
    return {"currency": currency, "min": minimum, "max": maximum, "unit": unit or "month"}


def _parse_job(raw: dict) -> Job | None:
    if raw.get("awarded"):
        return None

    url = raw.get("url")
    if not isinstance(url, str) or not url:
        return None

    advert = raw.get("advert")
    if not isinstance(advert, dict):
        advert = {}
    values = advert.get("values")
    if not isinstance(values, list):
        values = []
    options = raw.get("options")
    if not isinstance(options, dict):
        options = {}

    job_types = options.get("job_type")
    employment_type = job_types[0] if isinstance(job_types, list) and job_types else None

    workplace_type = None
    if options.get("remote") == "1":
        workplace_type = "remote"
    elif options.get("_work_model") == "Hybrid":
        workplace_type = "hybrid"
    elif options.get("_work_model") == "Remote":
        workplace_type = "remote"

    date_posted = raw.get("valid_start")
    if isinstance(date_posted, str):
        date_posted = date_posted.split(" ")[0]

    metadata: dict = {}
    recruitment = advert.get("recruitment")
    if isinstance(recruitment, dict) and recruitment.get("nr_ref"):
        metadata["reference"] = recruitment["nr_ref"]
    if options.get("branches"):
        metadata["department"] = options["branches"]

    return Job(
        url=url,
        title=advert.get("name") if isinstance(advert.get("name"), str) else None,
        description=_get_value(values, "description"),
        locations=_parse_locations(values),
        employment_type=employment_type,
        workplace_type=workplace_type,
        date_posted=date_posted,
        salary=_parse_salary(options),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not slug:
        raise ValueError(
            f"Cannot derive Traffit slug from {board.board_url!r} "
            "and no slug in monitor_config"
        )

    jobs: list[Job] = []
    page = 1
    while True:
        response = await client.get(
            _api_url(slug),
            headers={
                "X-Request-Page-Size": str(PAGE_SIZE),
                "X-Request-Current-Page": str(page),
            },
            follow_redirects=True,
        )
        if response.status_code == 404 and page == 1:
            raise LookupError(f"Traffit board {slug!r} returned 404 (board gone)")
        response.raise_for_status()

        raw_jobs = response.json()
        if not isinstance(raw_jobs, list):
            raise ValueError("Traffit response must be a JSON array")
        if not raw_jobs:
            break

        for raw in raw_jobs:
            if not isinstance(raw, dict):
                continue
            parsed = _parse_job(raw)
            if parsed is not None:
                jobs.append(parsed)

        total_pages = response.headers.get("x-result-total-pages")
        if not total_pages:
            break
        try:
            if page >= int(total_pages):
                break
        except ValueError:
            break
        page += 1

    return jobs
