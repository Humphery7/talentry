"""d.vinci — public job publication API with full descriptions."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_MAX_JOBS = 50_000
_IGNORE_SLUGS = frozenset({"www", "static", "api", "cdn"})
_UNIT_RE = re.compile(r"^(?:year|month|week|day|hour)$")


def _slug_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if not host.endswith(".dvinci-hr.com"):
        return None
    slug = host.removesuffix(".dvinci-hr.com")
    if not slug or slug in _IGNORE_SLUGS or any(char in slug for char in "./:"):
        return None
    return slug


def _salary(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    currency = raw.get("currency")
    value = raw.get("value")
    if not isinstance(currency, str) or not currency or not isinstance(value, dict):
        return None
    minimum = value.get("minValue")
    maximum = value.get("maxValue")
    if minimum is None and maximum is None:
        return None
    unit = value.get("unitText")
    unit = unit.casefold() if isinstance(unit, str) and _UNIT_RE.fullmatch(unit.casefold()) else "year"
    result: dict[str, object] = {"currency": currency, "unit": unit}
    if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
        result["min"] = minimum
    if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
        result["max"] = maximum
    return result


def _locations(opening: dict) -> list[str] | None:
    rows = opening.get("locations")
    if not isinstance(rows, list):
        return None
    locations: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if isinstance(name, str) and name and name not in locations:
            locations.append(name)
    return locations or None


def _description(raw: dict) -> str | None:
    parts = [
        value
        for key in ("introduction", "tasks", "profile", "weOffer", "closingText")
        if isinstance((value := raw.get(key)), str) and value.strip()
    ]
    return "\n".join(parts) or None


def _parse_job(raw: object) -> Job | None:
    if not isinstance(raw, dict):
        return None
    url = raw.get("jobPublicationURL")
    title = raw.get("position") or raw.get("pageTitle")
    if not isinstance(url, str) or not url or not isinstance(title, str) or not title.strip():
        return None

    opening = raw.get("jobOpening")
    opening = opening if isinstance(opening, dict) else {}
    working_times = opening.get("workingTimes")
    employment_type = None
    if isinstance(working_times, list):
        for row in working_times:
            if isinstance(row, dict) and isinstance(row.get("internalName"), str):
                employment_type = row["internalName"]
                break

    metadata: dict[str, object] = {}
    if raw.get("id") is not None:
        metadata["id"] = raw["id"]
    reference = opening.get("reference")
    if isinstance(reference, str) and reference:
        metadata["reference"] = reference
    department = opening.get("department")
    if isinstance(department, str) and department:
        metadata["department"] = department
    categories = opening.get("categories")
    if isinstance(categories, list):
        names = [
            row["name"]
            for row in categories
            if isinstance(row, dict) and isinstance(row.get("name"), str) and row["name"]
        ]
        if names:
            metadata["categories"] = names
    contract = opening.get("contractPeriod")
    if isinstance(contract, dict) and isinstance(contract.get("internalName"), str):
        metadata["contract_period"] = contract["internalName"].casefold()

    return Job(
        url=url,
        title=title.strip(),
        description=_description(raw),
        locations=_locations(opening),
        employment_type=employment_type,
        date_posted=opening.get("createdDate") if isinstance(opening.get("createdDate"), str) else None,
        salary=_salary(opening.get("salary") or raw.get("salary")),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    metadata = board.monitor_config
    slug = metadata.get("slug") or _slug_from_url(board.board_url)
    if not isinstance(slug, str) or not slug:
        raise ValueError(f"Cannot derive d.vinci slug from {board.board_url!r}")

    response = await client.get(
        f"https://{slug}.dvinci-hr.com/jobPublication/list.json",
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("d.vinci response is not a list")
    if len(payload) > _MAX_JOBS:
        raise ValueError("d.vinci inventory exceeded the safety cap")

    jobs: list[Job] = []
    seen: set[str] = set()
    for raw in payload:
        job = _parse_job(raw)
        if job is None or job.url in seen:
            continue
        seen.add(job.url)
        jobs.append(job)
    return jobs
