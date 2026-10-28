"""BambooHR — GET https://{tenant}.bamboohr.com/careers/list + per-job detail."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_DOMAIN_RE = re.compile(r"^([a-z0-9][a-z0-9-]*)\.bamboohr\.com$")
_IGNORE_TENANTS = frozenset({"api", "app", "help", "static", "www"})
_LOCATION_TYPES = {"0": "onsite", "1": "remote", "2": "hybrid"}
_DETAIL_CONCURRENCY = 10


def tenant_from_url(board_url: str) -> str | None:
    host = (urlparse(board_url).hostname or "").lower()
    match = _DOMAIN_RE.fullmatch(host)
    if match and match.group(1) not in _IGNORE_TENANTS:
        return match.group(1)
    return None


def _list_url(tenant: str) -> str:
    return f"https://{tenant}.bamboohr.com/careers/list"


def _job_url(tenant: str, job_id: object) -> str:
    return f"https://{tenant}.bamboohr.com/careers/{job_id}"


def _detail_url(tenant: str, job_id: object) -> str:
    return f"{_job_url(tenant, job_id)}/detail"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _locations(raw: dict) -> list[str] | None:
    location = raw.get("location")
    if isinstance(location, str):
        name = _clean_text(location)
        return [name] if name else None

    ats_location = raw.get("atsLocation")
    if isinstance(ats_location, str):
        name = _clean_text(ats_location)
        if name:
            return [name]
        ats_location = {}
    if not isinstance(location, dict):
        location = {}
    if not isinstance(ats_location, dict):
        ats_location = {}

    parts: list[str] = []
    for primary, fallback in (
        (location.get("city"), ats_location.get("city")),
        (
            location.get("state") or location.get("province"),
            ats_location.get("state") or ats_location.get("province"),
        ),
        (
            location.get("addressCountry") or location.get("country"),
            ats_location.get("country"),
        ),
    ):
        part = _clean_text(primary) or _clean_text(fallback)
        if part and part.casefold() not in {existing.casefold() for existing in parts}:
            parts.append(part)

    return [", ".join(parts)] if parts else None


def _workplace_type(raw: dict) -> str | None:
    value = raw.get("locationType")
    if value is not None:
        mapped = _LOCATION_TYPES.get(str(value))
        if mapped:
            return mapped
    return "remote" if raw.get("isRemote") is True else None


def _parse_job(raw: dict, tenant: str) -> Job | None:
    job_id = raw.get("id")
    if isinstance(job_id, bool) or not isinstance(job_id, (str, int)):
        return None
    job_id = str(job_id).strip()
    if not job_id.isdigit():
        return None

    metadata = {"job_id": job_id}
    for source, target in (
        ("departmentLabel", "department"),
        ("departmentId", "department_id"),
        ("minimumExperience", "minimum_experience"),
    ):
        value = raw.get(source)
        if value not in (None, ""):
            metadata[target] = value

    return Job(
        url=_job_url(tenant, job_id),
        title=_clean_text(raw.get("jobOpeningName")),
        locations=_locations(raw),
        employment_type=_clean_text(raw.get("employmentStatusLabel"))
        or _clean_text(raw.get("employmentType")),
        workplace_type=_workplace_type(raw),
        date_posted=_clean_text(raw.get("datePosted")),
        metadata=metadata,
    )


async def _fetch_detail(
    tenant: str, job_id: str, client: httpx.AsyncClient
) -> dict | None:
    response = await client.get(_detail_url(tenant, job_id), follow_redirects=True)
    if response.status_code in {404, 410}:
        return None
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        return None
    result = payload.get("result")
    opening = result.get("jobOpening") if isinstance(result, dict) else None
    return opening if isinstance(opening, dict) else None


def _merge_detail(job: Job, detail: dict) -> Job:
    title = _clean_text(detail.get("jobOpeningName"))
    if title:
        job.title = title

    description = detail.get("description")
    if isinstance(description, str) and description.strip():
        job.description = description.strip()

    locations = _locations(detail)
    if locations:
        job.locations = locations
    employment_type = _clean_text(detail.get("employmentStatusLabel")) or _clean_text(
        detail.get("employmentType")
    )
    if employment_type:
        job.employment_type = employment_type
    workplace_type = _workplace_type(detail)
    if workplace_type:
        job.workplace_type = workplace_type
    date_posted = _clean_text(detail.get("datePosted"))
    if date_posted:
        job.date_posted = date_posted

    metadata = dict(job.metadata or {})
    for source, target in (
        ("departmentLabel", "department"),
        ("departmentId", "department_id"),
        ("minimumExperience", "minimum_experience"),
    ):
        value = detail.get(source)
        if value not in (None, ""):
            metadata[target] = value
    job.metadata = metadata or None
    return job


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    tenant = board.monitor_config.get("tenant") or tenant_from_url(board.board_url)
    if not tenant:
        raise ValueError(
            f"Cannot derive BambooHR tenant from {board.board_url!r} "
            "and no tenant in monitor_config"
        )

    response = await client.get(_list_url(tenant), follow_redirects=True)
    if response.status_code in {404, 410}:
        raise LookupError(f"BambooHR board {tenant!r} returned {response.status_code} (board gone)")
    response.raise_for_status()

    payload = response.json()
    raw_jobs = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(raw_jobs, list):
        raise ValueError("BambooHR response must contain a result list")

    jobs = [
        job
        for raw in raw_jobs
        if isinstance(raw, dict) and (job := _parse_job(raw, tenant)) is not None
    ]

    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def enrich(job: Job) -> Job:
        job_id = (job.metadata or {}).get("job_id")
        if not isinstance(job_id, str):
            return job
        async with semaphore:
            detail = await _fetch_detail(tenant, job_id, client)
        return _merge_detail(job, detail) if detail is not None else job

    return list(await asyncio.gather(*(enrich(job) for job in jobs)))
