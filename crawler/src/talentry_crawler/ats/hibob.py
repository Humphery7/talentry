"""HiBob — GET https://{tenant}.careers.hibob.com/api/job-ad"""

from __future__ import annotations

import html
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_HOST_SUFFIX = ".careers.hibob.com"
_SALARY_UNITS = {
    "annual": "year",
    "annually": "year",
    "year": "year",
    "yearly": "year",
    "monthly": "month",
    "month": "month",
    "weekly": "week",
    "week": "week",
    "daily": "day",
    "day": "day",
    "hourly": "hour",
    "hour": "hour",
}
_WORKPLACE_TYPES = {
    "remote": "remote",
    "hybrid": "hybrid",
    "on site": "onsite",
    "onsite": "onsite",
    "office": "onsite",
}


def origin_from_url(board_url: str) -> str | None:
    parsed = urlparse(board_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not host.endswith(_HOST_SUFFIX):
        return None
    return f"{parsed.scheme}://{host}"


def _api_url(origin: str) -> str:
    return f"{origin}/api/job-ad"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _build_description(raw: dict) -> str | None:
    parts: list[str] = []
    description = _clean_text(raw.get("description"))
    if description:
        parts.append(description)

    for key, label in (
        ("responsibilities", "Responsibilities"),
        ("requirements", "Requirements"),
        ("benefits", "Benefits"),
    ):
        value = _clean_text(raw.get(key))
        if value:
            parts.append(f"<h3>{html.escape(label)}</h3>\n{value}")

    return "\n".join(parts) or None


def _locations(raw: dict) -> list[str] | None:
    for key in ("site", "country"):
        value = _clean_text(raw.get(key))
        if value:
            return [value]
    return None


def _workplace_type(raw: dict) -> str | None:
    value = _clean_text(raw.get("workspaceType")) or _clean_text(raw.get("workspaceTypeId"))
    if value is None:
        return None
    mapped = _WORKPLACE_TYPES.get(value.casefold())
    if mapped:
        return mapped
    if str(raw.get("isRemote")).casefold() == "true":
        return "remote"
    return None


def _salary(raw: dict) -> dict | None:
    minimum = raw.get("payTransparencyMinSalary")
    maximum = raw.get("payTransparencyMaxSalary")
    if minimum is None and maximum is None:
        return None

    period = str(raw.get("payTransparencySalaryPayPeriod") or "").casefold()
    return {
        "currency": raw.get("payTransparencySalaryCurrency"),
        "min": minimum,
        "max": maximum,
        "unit": _SALARY_UNITS.get(period, "year"),
    }


def _parse_job(raw: dict, origin: str) -> Job | None:
    job_id = raw.get("id")
    if not isinstance(job_id, str) or not job_id.strip():
        return None

    metadata = {
        key: value
        for key, value in {
            "id": job_id,
            "department": raw.get("department"),
            "department_id": raw.get("departmentId"),
            "site_id": raw.get("siteId"),
            "country": raw.get("country"),
            "employment_type_id": raw.get("employmentTypeId"),
            "workspace_type_id": raw.get("workspaceTypeId"),
        }.items()
        if value not in (None, "")
    }

    return Job(
        url=f"{origin}/jobs/{job_id.strip()}",
        title=_clean_text(raw.get("title")),
        description=_build_description(raw),
        locations=_locations(raw),
        employment_type=_clean_text(raw.get("employmentTypeId"))
        or _clean_text(raw.get("employmentType")),
        workplace_type=_workplace_type(raw),
        date_posted=_clean_text(raw.get("publishedAt")),
        salary=_salary(raw),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    origin = board.monitor_config.get("origin") or origin_from_url(board.board_url)
    origin = origin_from_url(origin) if isinstance(origin, str) else None
    if not origin:
        raise ValueError(
            f"Cannot derive HiBob origin from {board.board_url!r} "
            "and no origin in monitor_config"
        )

    response = await client.get(
        _api_url(origin),
        headers={"Accept": "application/json", "Referer": f"{origin}/"},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(f"HiBob board {origin!r} returned {response.status_code} (board gone)")
    response.raise_for_status()

    payload = response.json()
    raw_jobs = payload.get("jobAdDetails") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        raise ValueError("HiBob response must contain a jobAdDetails list")

    return [
        job
        for raw in raw_jobs
        if isinstance(raw, dict) and (job := _parse_job(raw, origin)) is not None
    ]
