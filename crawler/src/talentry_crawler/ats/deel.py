"""Deel — public jobs API at https://api-prod.letsdeel.com"""

from __future__ import annotations

import re

import httpx

from talentry_crawler.models import Board, Job

_FRONTEND_BASE = "https://jobs.deel.com"
_API_BASE = "https://api-prod.letsdeel.com"
_SLUG_RE = re.compile(r"jobs\.deel\.com/(?:job-boards/)?([\w-]+)")
_IGNORE_SLUGS = frozenset(
    {"auth", "login", "signup", "guest", "api", "deelapi", "job-boards", "job-details"}
)


def slug_from_url(board_url: str) -> str | None:
    match = _SLUG_RE.search(board_url)
    if match and match.group(1) not in _IGNORE_SLUGS:
        return match.group(1)
    return None


def _settings_url(slug: str) -> str:
    return f"{_API_BASE}/guest/ats/organizations/{slug}/career_page_settings"


def _postings_url(org_id: str, board_id: str) -> str:
    return f"{_API_BASE}/guest/ats/organizations/{org_id}/job_boards/{board_id}/job_postings"


def _parse_salary(posting: dict) -> dict | None:
    if not posting.get("isCompensationVisible", False):
        return None
    job = posting.get("job")
    compensation = job.get("currentCompensation") if isinstance(job, dict) else None
    if not isinstance(compensation, dict):
        return None

    minimum = compensation.get("minAmount")
    maximum = compensation.get("maxAmount")
    if minimum is None and maximum is None:
        return None
    return {
        "currency": compensation.get("currencyIsoCode"),
        "min": minimum,
        "max": maximum,
        "unit": "year",
    }


def _parse_job(posting: dict, slug: str) -> Job | None:
    posting_id = posting.get("id")
    if not isinstance(posting_id, str) or not posting_id:
        return None

    job = posting.get("job")
    if not isinstance(job, dict):
        job = {}

    locations = [
        location["name"]
        for item in job.get("jobLocations") or []
        if isinstance(item, dict)
        and isinstance((location := item.get("location")), dict)
        and location.get("name")
    ]

    employment_type = None
    for item in job.get("jobEmploymentTypes") or []:
        if not isinstance(item, dict):
            continue
        value = item.get("employmentType")
        if isinstance(value, dict) and value.get("name"):
            employment_type = value["name"]
            break

    metadata: dict = {"id": posting_id}
    teams = [
        team["name"]
        for item in job.get("jobTeams") or []
        if isinstance(item, dict)
        and isinstance((team := item.get("team")), dict)
        and team.get("name")
    ]
    if teams:
        metadata["team"] = ", ".join(teams)
    departments = [
        department["name"]
        for item in job.get("jobDepartments") or []
        if isinstance(item, dict)
        and isinstance((department := item.get("department")), dict)
        and department.get("name")
    ]
    if departments:
        metadata["department"] = ", ".join(departments)

    return Job(
        url=f"{_FRONTEND_BASE}/{slug}/job-details/{posting_id}/overview",
        title=posting.get("title") if isinstance(posting.get("title"), str) else None,
        description=posting.get("richtextDescription")
        if isinstance(posting.get("richtextDescription"), str)
        else None,
        locations=locations or None,
        employment_type=employment_type,
        date_posted=posting.get("createdAt"),
        salary=_parse_salary(posting),
        metadata=metadata,
    )


async def _fetch_settings(
    slug: str, client: httpx.AsyncClient
) -> tuple[str | None, str | None]:
    response = await client.get(_settings_url(slug), follow_redirects=True)
    if response.status_code == 404:
        raise LookupError(f"Deel board {slug!r} returned 404 (board gone)")
    response.raise_for_status()

    settings = response.json()
    if not isinstance(settings, dict):
        raise ValueError("Deel settings response must be a JSON object")
    job_board = settings.get("jobBoard")
    board_id = job_board.get("id") if isinstance(job_board, dict) else None
    return settings.get("organizationId"), board_id


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not slug:
        raise ValueError(
            f"Cannot derive Deel slug from {board.board_url!r} "
            "and no slug in monitor_config"
        )

    org_id = board.monitor_config.get("org_id")
    board_id = board.monitor_config.get("board_id")
    if not org_id or not board_id:
        org_id, board_id = await _fetch_settings(slug, client)
    if not org_id or not board_id:
        raise ValueError(f"Missing Deel org_id or board_id for {slug!r}")

    response = await client.get(_postings_url(str(org_id), str(board_id)), follow_redirects=True)
    if response.status_code == 404:
        raise LookupError(f"Deel postings for {slug!r} returned 404 (board gone)")
    response.raise_for_status()

    data = response.json()
    raw_jobs = data if isinstance(data, list) else None
    if raw_jobs is None and isinstance(data, dict):
        raw_jobs = data.get("jobPostings")
    if not isinstance(raw_jobs, list):
        raise ValueError("Deel postings response must contain a job list")

    jobs: list[Job] = []
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_job(raw, slug)
        if parsed is not None:
            jobs.append(parsed)
    return jobs
