"""Keka — career-portal bootstrap plus public embedjobs JSON feed."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx

from talentry_crawler.models import Board, Job

_HOST_RE = re.compile(r"^([a-z0-9-]+)\.keka\.com$", re.IGNORECASE)
_IDENTIFIER_RE = re.compile(r"identifier\s*:\s*['\"]([0-9a-f-]{36})['\"]", re.IGNORECASE)
_PORTAL_RE = re.compile(r"portalName\s*:\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_FETCH_RE = re.compile(
    r"fetch\(['\"]([^'\"]*careerportal[^'\"]*\.html)['\"]\)", re.IGNORECASE
)
_MAX_JOBS = 50_000
_PERIOD_UNITS = {1: "hour", 3: "month", 4: "year"}


def _board_key(board: Board) -> tuple[str, str, str]:
    try:
        parsed = urlparse(board.board_url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Unsupported Keka board URL: {board.board_url!r}") from exc
    host = (parsed.hostname or "").lower()
    match = _HOST_RE.fullmatch(host)
    if (
        parsed.scheme != "https"
        or match is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"Unsupported Keka board URL: {board.board_url!r}")

    parts = [part for part in parsed.path.split("/") if part]
    if not parts or parts[0] != "careers" or len(parts) > 2:
        raise ValueError(f"Unsupported Keka board URL: {board.board_url!r}")
    configured_portal = board.monitor_config.get("portal")
    if configured_portal is not None and not isinstance(configured_portal, str):
        raise ValueError("Keka portal must be a string")
    portal = configured_portal or (parts[1] if len(parts) == 2 else "default")
    return match.group(1).lower(), portal, f"https://{host}"


def _jobs_url(origin: str, portal: str, identifier: str) -> str:
    return f"{origin}/careers/api/embedjobs/{portal}/active/{identifier}"


def _job_url(origin: str, portal: str, job_id: int) -> str:
    middle = "" if portal == "default" else f"/{portal}"
    return f"{origin}/careers{middle}/jobdetails/{job_id}"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _html_text(value: object) -> str | None:
    cleaned = value.strip() if isinstance(value, str) else None
    if not cleaned:
        return None
    if "<" in cleaned and ">" in cleaned:
        return cleaned
    return f"<p>{html.escape(cleaned).replace(chr(10), '<br>')}</p>"


def _date(value: object) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _locations(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    locations: list[str] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        components: list[str] = []
        seen: set[str] = set()
        for key in ("city", "state", "countryName"):
            component = _clean_text(raw.get(key))
            if component is None:
                continue
            identity = component.casefold()
            if identity not in seen:
                seen.add(identity)
                components.append(component)
        label = ", ".join(components) if components else _clean_text(raw.get("name"))
        if label and label not in locations:
            locations.append(label)
    return locations or None


def _salary(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    minimum = value.get("minimum")
    maximum = value.get("maximum")
    minimum = (
        minimum
        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and minimum > 0
        else None
    )
    maximum = (
        maximum
        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) and maximum > 0
        else None
    )
    if minimum is None and maximum is None:
        return None
    period = value.get("salaryPeriod")
    unit = _PERIOD_UNITS.get(period) if isinstance(period, int) else None
    return {
        "currency": _clean_text(value.get("currency")),
        "min": minimum,
        "max": maximum,
        "unit": unit,
    }


def _parse_job(raw: object, origin: str, portal: str) -> Job:
    if not isinstance(raw, dict):
        raise ValueError("Keka feed returned a non-object job")
    job_id = raw.get("id")
    title = _clean_text(raw.get("title"))
    if (
        isinstance(job_id, bool)
        or not isinstance(job_id, int)
        or job_id < 1
        or title is None
    ):
        raise ValueError("Keka feed returned a job without a valid identity or title")

    metadata: dict[str, object] = {"id": job_id}
    for source, target in (
        ("departmentIdentifier", "department_id"),
        ("departmentName", "department"),
        ("experience", "experience"),
        ("jobNumber", "job_number"),
    ):
        value = _clean_text(raw.get(source))
        if value is not None:
            metadata[target] = value

    job_type = raw.get("jobType")
    employment_type = (
        "Full Time" if job_type == 2 else "Part Time" if job_type == 1 else None
    )
    if isinstance(job_type, int) and not isinstance(job_type, bool):
        metadata["job_type"] = job_type

    skills = raw.get("skillNames")
    if isinstance(skills, list):
        cleaned_skills = [
            value for item in skills if (value := _clean_text(item)) is not None
        ]
        if cleaned_skills:
            metadata["skills"] = list(dict.fromkeys(cleaned_skills))

    return Job(
        url=_job_url(origin, portal, job_id),
        title=title,
        description=_html_text(raw.get("description")),
        locations=_locations(raw.get("jobLocations")),
        employment_type=employment_type,
        date_posted=_date(raw.get("publishedOn")),
        salary=_salary(raw.get("salaryRange")),
        metadata=metadata,
    )


async def _bootstrap(board: Board, client: httpx.AsyncClient) -> tuple[str, str, str]:
    tenant, portal, origin = _board_key(board)
    configured = board.monitor_config.get("identifier")
    if configured is not None:
        if not isinstance(configured, str) or _IDENTIFIER_RE.fullmatch(
            f"identifier: '{configured}'"
        ) is None:
            raise ValueError("Keka identifier must be a UUID")
        return origin, portal, str(configured).lower()

    response = await client.get(
        board.board_url,
        headers={"Accept": "text/html"},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(f"Keka tenant {tenant!r} returned {response.status_code}")
    response.raise_for_status()

    fetch_match = _FETCH_RE.search(response.text)
    if fetch_match is None:
        identifier_match = _IDENTIFIER_RE.search(response.text)
        if identifier_match is None:
            raise ValueError(f"Keka tenant {tenant!r} omitted its career-portal identity")
        return origin, portal, identifier_match.group(1).lower()

    bootstrap_url = urljoin(str(response.url), html.unescape(fetch_match.group(1)))
    bootstrap = await client.get(
        bootstrap_url,
        headers={"Accept": "text/html"},
        follow_redirects=True,
    )
    if bootstrap.status_code in {404, 410}:
        raise LookupError(f"Keka tenant {tenant!r} bootstrap returned {bootstrap.status_code}")
    bootstrap.raise_for_status()

    identifier_match = _IDENTIFIER_RE.search(bootstrap.text)
    if identifier_match is None:
        raise ValueError(f"Keka tenant {tenant!r} bootstrap omitted its portal identity")
    portal_match = _PORTAL_RE.search(bootstrap.text)
    if portal_match is not None and board.monitor_config.get("portal") is None:
        portal = portal_match.group(1).strip() or portal
    return origin, portal, identifier_match.group(1).lower()


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    origin, portal, identifier = await _bootstrap(board, client)
    response = await client.get(
        _jobs_url(origin, portal, identifier),
        headers={"Accept": "application/json"},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(f"Keka tenant {portal!r} jobs feed returned {response.status_code}")
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Keka jobs feed must be a list")
    if len(payload) > _MAX_JOBS:
        raise ValueError(f"Keka jobs feed exceeds the {_MAX_JOBS:,}-job cap")

    jobs: list[Job] = []
    seen_ids: set[int] = set()
    for raw in payload:
        job = _parse_job(raw, origin, portal)
        job_id = int((job.metadata or {})["id"])
        if job_id in seen_ids:
            raise ValueError(f"Keka jobs feed repeated job {job_id}")
        seen_ids.add(job_id)
        jobs.append(job)
    return jobs
