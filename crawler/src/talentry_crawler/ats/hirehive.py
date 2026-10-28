"""HireHive — GET https://{slug}.hirehive.com/api/v2/jobs (paginated)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

PAGE_SIZE = 100
_DOMAIN_RE = re.compile(r"^([a-z0-9-]+)\.hirehive\.com$")
_IGNORE_SLUGS = frozenset(
    {"api", "app", "assets", "docs", "help", "hirehive-testing-account", "static", "www"}
)
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
    match = _DOMAIN_RE.fullmatch(host)
    if match and match.group(1) not in _IGNORE_SLUGS:
        return match.group(1)
    return None


def _api_url(slug: str) -> str:
    return f"https://{slug}.hirehive.com/api/v2/jobs"


def _parse_description(raw: dict) -> str | None:
    description = raw.get("description")
    if isinstance(description, dict):
        value = description.get("html") or description.get("text")
        return value if isinstance(value, str) and value else None
    if isinstance(description, str):
        return description or None
    return None


def _parse_locations(raw: dict) -> list[str] | None:
    location = raw.get("location")
    if isinstance(location, str) and location.strip():
        return [location.strip()]

    country = raw.get("country")
    country_name = country.get("name") if isinstance(country, dict) else None
    parts = [part for part in (raw.get("state_code"), country_name) if part]
    return [", ".join(parts)] if parts else None


def _parse_salary(raw: dict) -> dict | None:
    for tier in raw.get("compensation_tiers") or []:
        if not isinstance(tier, dict):
            continue
        minimum = tier.get("min_value")
        maximum = tier.get("max_value")
        if minimum is None and maximum is None:
            continue
        interval = tier.get("interval")
        unit = _SALARY_UNITS.get(str(interval).lower()) if interval else "year"
        return {
            "currency": tier.get("currency_code"),
            "min": minimum,
            "max": maximum,
            "unit": unit or "year",
        }
    return None


def _parse_job(raw: dict, default_workplace_type: str | None) -> Job | None:
    url = raw.get("hosted_url")
    if not isinstance(url, str) or not url:
        return None

    job_type = raw.get("type")
    employment_type = None
    if isinstance(job_type, dict):
        employment_type = job_type.get("type") or job_type.get("name") or None

    metadata: dict = {}
    if raw.get("id"):
        metadata["id"] = raw["id"]
    category = raw.get("category")
    if isinstance(category, dict) and category.get("name"):
        metadata["category"] = category["name"]
    experience = raw.get("experience")
    if isinstance(experience, dict) and experience.get("type"):
        metadata["experience"] = experience["type"]

    return Job(
        url=url,
        title=raw.get("title") if isinstance(raw.get("title"), str) else None,
        description=_parse_description(raw),
        locations=_parse_locations(raw),
        employment_type=employment_type,
        workplace_type=default_workplace_type,
        date_posted=raw.get("published_date"),
        salary=_parse_salary(raw),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not slug:
        raise ValueError(
            f"Cannot derive HireHive slug from {board.board_url!r} "
            "and no slug in monitor_config"
        )

    defaults = board.monitor_config.get("defaults")
    default_workplace_type = None
    if isinstance(defaults, dict) and isinstance(defaults.get("job_location_type"), str):
        default_workplace_type = defaults["job_location_type"]

    jobs: list[Job] = []
    page = 1
    while True:
        response = await client.get(
            _api_url(slug),
            params={"page": page, "page_size": PAGE_SIZE},
            follow_redirects=True,
        )
        if response.status_code == 404 and page == 1:
            raise LookupError(f"HireHive board {slug!r} returned 404 (board gone)")
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("HireHive response must be a JSON object")
        items = data.get("items")
        meta = data.get("meta")
        if not isinstance(items, list) or not isinstance(meta, dict):
            raise ValueError("HireHive response must contain items and meta")

        for raw in items:
            if not isinstance(raw, dict):
                continue
            parsed = _parse_job(raw, default_workplace_type)
            if parsed is not None:
                jobs.append(parsed)

        if not meta.get("has_next_page"):
            break
        page += 1

    return jobs
