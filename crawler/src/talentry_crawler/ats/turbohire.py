"""TurboHire — public token, filtered jobs, and per-job detail APIs."""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import UUID

import httpx

from talentry_crawler.models import Board, Job

_API_BASE = "https://thapi.azurewebsites.net"
_MAX_JOBS = 50_000
_DETAIL_CONCURRENCY = 10
_CAREER_PAGE_RE = re.compile(
    r"^/careerpage/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/?$",
    re.IGNORECASE,
)


def _valid_org_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _org_id_from_url(board_url: str) -> str | None:
    parsed = urlparse(board_url)
    if not (parsed.hostname or "").lower().endswith(".turbohire.co"):
        return None
    match = _CAREER_PAGE_RE.fullmatch(parsed.path)
    if match is not None:
        return _valid_org_id(match.group(1))
    values = parse_qs(parsed.query).get("orgId") or parse_qs(parsed.query).get("orgid")
    return _valid_org_id(values[0]) if values else None


def _board_key(board: Board) -> tuple[str, str]:
    parsed = urlparse(board.board_url)
    host = (parsed.hostname or "").lower()
    if not host.endswith(".turbohire.co"):
        raise ValueError(f"Unsupported TurboHire board URL: {board.board_url!r}")
    configured = _valid_org_id(board.monitor_config.get("org_id"))
    direct = _org_id_from_url(board.board_url)
    if configured is not None and direct is not None and configured != direct:
        raise ValueError("Configured TurboHire organization does not match the board URL")
    org_id = configured or direct
    if org_id is None:
        raise ValueError(f"Cannot derive TurboHire organization ID from {board.board_url!r}")
    return org_id, f"{parsed.scheme or 'https'}://{host}"


def _headers(board_url: str, token: str | None = None) -> dict[str, str]:
    parsed = urlparse(board_url)
    headers = {
        "accept": "application/json, text/plain, */*",
        "origin": f"{parsed.scheme or 'https'}://{parsed.netloc}",
        "referer": board_url,
    }
    if token is not None:
        headers["authorization"] = f"Bearer {token}"
    return headers


def _jobs_body() -> dict:
    empty_filter = {"Value": None, "FilterType": 0}
    return {
        "SortByV2": {"Key": "PostedDate", "Order": 2},
        "BunitIds": dict(empty_filter),
        "Experience": dict(empty_filter),
        "JobTypes": dict(empty_filter),
        "JobTypeV2": dict(empty_filter),
        "Locations": dict(empty_filter),
        "CreatedDate": dict(empty_filter),
        "Compensation": dict(empty_filter),
        "Skills": dict(empty_filter),
        "Keyword": "",
        "ClientIds": dict(empty_filter),
        "Department": "",
        "CustomFields": {},
    }


async def _token(board_url: str, client: httpx.AsyncClient) -> str:
    response = await client.get(
        f"{_API_BASE}/api/token/noauth",
        headers=_headers(board_url),
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise ValueError("TurboHire token response omitted access_token")
    return token


async def _listing(
    board_url: str, org_id: str, token: str, client: httpx.AsyncClient
) -> list[dict]:
    response = await client.post(
        f"{_API_BASE}/api/careerpagev2/filteredjobs",
        params={"orgId": org_id, "pageType": 0},
        json=_jobs_body(),
        headers=_headers(board_url, token),
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    total = payload.get("Total") if isinstance(payload, dict) else None
    rows = payload.get("Result") if isinstance(payload, dict) else None
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
        or not isinstance(rows, list)
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise ValueError("TurboHire jobs response omitted a valid total or records")
    if total > _MAX_JOBS or len(rows) > _MAX_JOBS:
        raise ValueError(f"TurboHire organization exceeds the {_MAX_JOBS:,}-job cap")
    if len(rows) != total:
        raise ValueError(
            f"TurboHire jobs response returned {len(rows)} of {total} advertised jobs"
        )
    return rows


async def _detail(
    board_url: str, token: str, job_id: str, client: httpx.AsyncClient
) -> dict:
    response = await client.get(
        f"{_API_BASE}/api/publicjobs",
        params={"jobId": job_id, "fieldVisibility": 0},
        headers=_headers(board_url, token),
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"TurboHire job {job_id!r} detail must be an object")
    return payload


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _locations(value: object) -> list[str] | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        rows = json.loads(value)
    except json.JSONDecodeError:
        cleaned = _clean_text(value)
        return [cleaned] if cleaned else None
    if not isinstance(rows, list):
        return None

    locations: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        location = _clean_text(row.get("Address"))
        if location is None:
            continue
        identity = location.casefold()
        if identity not in seen:
            seen.add(identity)
            locations.append(location)
    return locations or None


def _description(raw: dict) -> str | None:
    for field in ("JobDescriptionV2", "JobDescription"):
        value = raw.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _job_url(portal_origin: str, public_id: str) -> str:
    encoded = quote(unquote(public_id), safe="")
    return f"{portal_origin}/job/publicjobs/{encoded}"


def _parse_job(raw: dict, portal_origin: str) -> Job:
    job_id = _clean_text(raw.get("JobId"))
    public_id = _clean_text(raw.get("JobIdObfuscated"))
    title = _clean_text(raw.get("JobTitle"))
    if job_id is None or public_id is None or title is None:
        raise ValueError("TurboHire returned a job without a valid public identity or title")

    metadata: dict[str, object] = {"id": job_id}
    for source, target in (
        ("JobCode", "job_code"),
        ("Department", "department"),
        ("ClientName", "client_name"),
    ):
        value = _clean_text(raw.get(source))
        if value is not None:
            metadata[target] = value

    experience = raw.get("Experience")
    if isinstance(experience, dict):
        minimum = experience.get("MinExp")
        maximum = experience.get("MaxExp")
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
            metadata["experience_min"] = minimum
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            metadata["experience_max"] = maximum

    skills = raw.get("Skills")
    if isinstance(skills, list):
        cleaned_skills = [
            value for item in skills if (value := _clean_text(item)) is not None
        ]
        if cleaned_skills:
            metadata["skills"] = list(dict.fromkeys(cleaned_skills))

    for source, target in (
        ("RolesAndResponsibilitiesV2", "responsibilities"),
        ("EligibilityV2", "qualifications"),
    ):
        value = raw.get(source)
        if isinstance(value, str) and value.strip():
            metadata[target] = value.strip()

    employment_type = _clean_text(raw.get("JobTypeV2")) or _clean_text(raw.get("Type"))
    if employment_type and employment_type.casefold() == "unspecified":
        employment_type = None

    published = raw.get("PublishedDates")
    date_posted = (
        published.get("CAREERPAGE") if isinstance(published, dict) else None
    ) or raw.get("PublishedDate")

    return Job(
        url=_job_url(portal_origin, public_id),
        title=title,
        description=_description(raw),
        locations=_locations(raw.get("Location")),
        employment_type=employment_type,
        date_posted=date_posted if isinstance(date_posted, str) else None,
        metadata=metadata,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    org_id, portal_origin = _board_key(board)
    token = await _token(board.board_url, client)
    rows = await _listing(board.board_url, org_id, token, client)

    async def fetch(row: dict) -> Job:
        public_id = _clean_text(row.get("JobIdObfuscated"))
        if public_id is None:
            raise ValueError("TurboHire listing returned a job without JobIdObfuscated")
        detail = await _detail(board.board_url, token, public_id, client)
        if detail.get("JobId") != row.get("JobId"):
            raise ValueError("TurboHire detail response did not match its listing record")
        return _parse_job(detail, portal_origin)

    jobs: list[Job] = []
    for start in range(0, len(rows), _DETAIL_CONCURRENCY):
        jobs.extend(
            await asyncio.gather(
                *(fetch(row) for row in rows[start : start + _DETAIL_CONCURRENCY])
            )
        )
    return jobs
