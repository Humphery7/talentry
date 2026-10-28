"""Curately — public career portal search API with full job descriptions."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlsplit

import httpx

from talentry_crawler.models import Board, Job

_API_BASE = "https://api.curately.ai/QADemoCurately"
_SEARCH_URL = f"{_API_BASE}/sovrenjobsearch"
_MAX_JOBS = 50_000
_DEFAULT_DAYS_BACK = 180
_SNAPSHOT_ATTEMPTS = 3
_SNAPSHOT_RETRY_DELAY = 1.0
_SEMANTIC_ZERO_ATTEMPTS = 3
_SEMANTIC_ZERO_RETRY_DELAY = 1.0

_SHORT_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_BOARD_PATH_RE = re.compile(
    r"^/jobs/([a-z0-9]+(?:-[a-z0-9]+)*)(?:/.*)?$",
    re.IGNORECASE,
)
_JOB_TYPE_MAP = {1: "full_time", 2: "contract", 3: "contract", 4: "contract"}
_JOB_HOURS_MAP = {1: "full_time", 2: "part_time"}
_WORK_TYPE_MAP = {1: "remote", 2: "hybrid", 3: "onsite"}
_ACTIVE_STATUSES = {None, 1, "1"}
_INACTIVE_STATUSES = {0, "0", 2, "2", 3, "3", 4, "4", 5, "5", 1008, "1008"}
_SALARY_UNITS = {
    "year": "year",
    "yearly": "year",
    "annual": "year",
    "annually": "year",
    "month": "month",
    "monthly": "month",
    "hour": "hour",
    "hourly": "hour",
    "day": "day",
    "daily": "day",
}


class _SnapshotChanged(ValueError):
    def __init__(self, message: str, *, expected_total: int | None = None) -> None:
        self.expected_total = expected_total
        super().__init__(message)


def _short_name_from_url(board_url: str) -> str | None:
    try:
        parsed = urlsplit(board_url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "careers.curately.ai"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        return None
    match = _BOARD_PATH_RE.fullmatch(parsed.path.rstrip("/"))
    return match.group(1).lower() if match else None


def _client_url(short_name: str) -> str:
    return f"{_API_BASE}/getByShortName/{short_name}"


def _job_url(short_name: str, job_id: int) -> str:
    return f"https://careers.curately.ai/jobs/{short_name}/apply-job/{job_id}/job"


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        parsed = int(value)
        return parsed if parsed > 0 else None
    return None


def _number(value: object) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _normalize_unit(value: str | None) -> str | None:
    if value is None:
        return None
    return _SALARY_UNITS.get(value.strip().lower())


def _locations(raw: dict) -> list[str] | None:
    parts = [
        value.strip()
        for key in ("workCity", "workState", "workZipcode")
        if isinstance((value := raw.get(key)), str) and value.strip()
    ]
    if parts:
        return [", ".join(parts)]
    return ["Remote"] if raw.get("workType") == 1 else None


def _employment_type(raw: dict) -> str | None:
    job_type = raw.get("jobType")
    if isinstance(job_type, int) and job_type in _JOB_TYPE_MAP:
        if job_type == 1 and raw.get("jobHours") == 2:
            return "part_time"
        return _JOB_TYPE_MAP[job_type]
    job_hours = raw.get("jobHours")
    return _JOB_HOURS_MAP.get(job_hours) if isinstance(job_hours, int) else None


def _salary(
    raw: dict,
    *,
    currency: str | None,
    unit: str | None,
) -> dict | None:
    minimum = _number(raw.get("payrateMin"))
    maximum = _number(raw.get("payrateMax"))
    normalized_unit = _normalize_unit(unit)
    if (minimum is None and maximum is None) or not currency or not normalized_unit:
        return None
    return {
        "currency": currency.upper(),
        "min": minimum,
        "max": maximum,
        "unit": normalized_unit,
    }


def _parse_job(
    raw: dict,
    *,
    short_name: str,
    currency: str | None = None,
    salary_unit: str | None = None,
) -> Job | None:
    status = raw.get("status")
    if status in _INACTIVE_STATUSES:
        return None
    if status not in _ACTIVE_STATUSES:
        raise ValueError(f"Curately job has an unknown status value {status!r}")

    job_id = _positive_int(raw.get("jobId"))
    title = raw.get("jobTitle")
    if job_id is None or not isinstance(title, str) or not title.strip():
        raise ValueError("Curately job is missing a valid jobId or jobTitle")

    description = raw.get("publicJobDescr")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"Curately job {job_id} is missing a non-empty description")

    locations = _locations(raw)
    if not locations:
        raise ValueError(f"Curately job {job_id} is missing a location")

    metadata: dict = {"id": job_id}
    for source, target in (
        ("clientName", "client_name"),
        ("estStartDate", "estimated_start_date"),
        ("estEndDate", "estimated_end_date"),
        ("jobHours", "job_hours_code"),
        ("jobType", "job_type_code"),
        ("workType", "work_type_code"),
    ):
        if raw.get(source) is not None:
            metadata[target] = raw[source]

    work_type = raw.get("workType")
    return Job(
        url=_job_url(short_name, job_id),
        title=title.strip(),
        description=description,
        locations=locations,
        employment_type=_employment_type(raw),
        workplace_type=_WORK_TYPE_MAP.get(work_type) if isinstance(work_type, int) else None,
        date_posted=raw.get("createDate") if isinstance(raw.get("createDate"), str) else None,
        salary=_salary(raw, currency=currency, unit=salary_unit),
        metadata=metadata,
    )


def _search_body(client_id: int, *, offset: int, days_back: int) -> dict:
    return {
        "query": "",
        "city": "",
        "state": "",
        "zipcode": "",
        "radius": "30",
        "daysback": str(days_back),
        "jobHours": "",
        "isRemote": False,
        "jobType": "",
        "clientids": str(client_id),
        "next": offset,
        "type": "",
    }


def _bounded_attempts(config: dict, key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError(f"Curately {key} must be an integer from 1 to 5")
    return value


def _board_config(
    board: Board,
) -> tuple[str, int | None, int, str | None, str | None, int, int]:
    metadata = board.monitor_config
    url_short_name = _short_name_from_url(board.board_url)
    if url_short_name is None:
        raise ValueError(f"Cannot derive Curately short_name from {board.board_url!r}")
    configured_short_name = metadata.get("short_name")
    if configured_short_name is not None and configured_short_name != url_short_name:
        raise ValueError(
            "Curately short_name does not match the careers.curately.ai board URL tenant"
        )
    short_name = configured_short_name or url_short_name
    if not isinstance(short_name, str) or not _SHORT_NAME_RE.fullmatch(short_name):
        raise ValueError("Curately short_name must be a lowercase tenant slug")

    client_id = metadata.get("client_id")
    if client_id is not None:
        client_id = _positive_int(client_id)
        if client_id is None:
            raise ValueError("Curately client_id must be a positive integer")

    days_back = metadata.get("days_back", _DEFAULT_DAYS_BACK)
    if isinstance(days_back, bool) or not isinstance(days_back, int) or not 1 <= days_back <= 3650:
        raise ValueError("Curately days_back must be an integer from 1 to 3650")

    currency = metadata.get("currency")
    salary_unit = metadata.get("salary_unit")
    for name, value in (("currency", currency), ("salary_unit", salary_unit)):
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Curately {name} must be a string")

    return (
        short_name,
        client_id,
        days_back,
        currency,
        salary_unit,
        _bounded_attempts(metadata, "snapshot_attempts", _SNAPSHOT_ATTEMPTS),
        _bounded_attempts(metadata, "semantic_zero_attempts", _SEMANTIC_ZERO_ATTEMPTS),
    )


async def _fetch_client(short_name: str, client: httpx.AsyncClient) -> dict:
    response = await client.get(_client_url(short_name), follow_redirects=True)
    if response.status_code in {404, 410}:
        raise LookupError(f"Curately tenant {short_name!r} no longer exists")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Curately tenant response must be an object")
    if data.get("Success") is not True or data.get("Status") != 200:
        raise ValueError(f"Curately tenant response for {short_name!r} was not successful")
    response_short_name = data.get("shortName")
    client_id = _positive_int(data.get("clientId"))
    if (
        not isinstance(response_short_name, str)
        or response_short_name.lower() != short_name
        or client_id is None
    ):
        raise ValueError(f"Curately tenant response for {short_name!r} has invalid identity")
    return data


async def _fetch_search_page(
    client: httpx.AsyncClient,
    *,
    client_id: int,
    offset: int,
    days_back: int,
) -> dict:
    response = await client.post(
        _SEARCH_URL,
        json=_search_body(client_id, offset=offset, days_back=days_back),
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError("Curately search API is gone")
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Curately search response must be an object")
    if data.get("Success") is not True or data.get("Status") != 200:
        raise ValueError("Curately search response was not successful")
    items = data.get("List")
    total = data.get("TotalSize")
    if (
        not isinstance(items, list)
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
    ):
        raise ValueError("Curately search response has invalid List or TotalSize")
    return data


async def _fetch_snapshot_page(
    client: httpx.AsyncClient,
    *,
    client_id: int,
    offset: int,
    days_back: int,
    expected_total: int | None,
    semantic_zero_attempts: int,
) -> dict:
    for attempt in range(1, semantic_zero_attempts + 1):
        data = await _fetch_search_page(
            client,
            client_id=client_id,
            offset=offset,
            days_back=days_back,
        )
        observed_total = data["TotalSize"]
        transient_zero = (
            expected_total is not None and expected_total > 0 and observed_total == 0
        )
        if not transient_zero:
            return data
        if attempt < semantic_zero_attempts:
            await asyncio.sleep(_SEMANTIC_ZERO_RETRY_DELAY * attempt)
    return data


async def _discover_snapshot(
    client: httpx.AsyncClient,
    *,
    short_name: str,
    client_id: int,
    days_back: int,
    currency: str | None,
    salary_unit: str | None,
    semantic_zero_attempts: int,
    prior_nonzero_total: int | None,
) -> list[Job]:
    jobs: list[Job] = []
    seen_ids: set[int] = set()
    offset = 0
    expected_total: int | None = None

    while True:
        data = await _fetch_snapshot_page(
            client,
            client_id=client_id,
            offset=offset,
            days_back=days_back,
            expected_total=expected_total,
            semantic_zero_attempts=semantic_zero_attempts,
        )
        items = data["List"]
        total = data["TotalSize"]
        if expected_total is None:
            if total == 0 and prior_nonzero_total is not None:
                raise _SnapshotChanged(
                    f"Curately TotalSize changed between snapshots: {prior_nonzero_total} -> 0",
                    expected_total=prior_nonzero_total,
                )
            expected_total = total
        elif total != expected_total:
            raise _SnapshotChanged(
                f"Curately TotalSize changed during pagination: {expected_total} -> {total}",
                expected_total=total,
            )

        if not items:
            if offset < min(total, _MAX_JOBS):
                raise _SnapshotChanged(
                    f"Curately pagination ended at offset {offset} before total {total}",
                    expected_total=total,
                )
            break

        for raw in items:
            if not isinstance(raw, dict):
                raise ValueError("Curately List contains a non-object job")
            job_id = _positive_int(raw.get("jobId"))
            if job_id is None:
                raise ValueError("Curately List contains a job without a valid jobId")
            if _positive_int(raw.get("clientId")) != client_id:
                raise ValueError(
                    f"Curately job {job_id} does not belong to client_id {client_id}"
                )
            if job_id in seen_ids:
                raise _SnapshotChanged(
                    f"Curately pagination repeated jobId {job_id}",
                    expected_total=expected_total,
                )
            seen_ids.add(job_id)
            job = _parse_job(
                raw,
                short_name=short_name,
                currency=currency,
                salary_unit=salary_unit,
            )
            if job is not None:
                jobs.append(job)

        offset += len(items)
        if offset >= min(total, _MAX_JOBS):
            break

    if expected_total is None:
        raise ValueError("Curately search returned no pagination metadata")
    if expected_total <= _MAX_JOBS and offset != expected_total:
        raise _SnapshotChanged(
            f"Curately returned {offset} rows for advertised total {expected_total}",
            expected_total=expected_total,
        )
    return jobs[:_MAX_JOBS]


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    (
        short_name,
        client_id,
        days_back,
        currency,
        salary_unit,
        snapshot_attempts,
        semantic_zero_attempts,
    ) = _board_config(board)
    if client_id is None:
        client_data = await _fetch_client(short_name, client)
        client_id = _positive_int(client_data.get("clientId"))
        assert client_id is not None

    prior_nonzero_total: int | None = None
    for attempt in range(1, snapshot_attempts + 1):
        try:
            return await _discover_snapshot(
                client,
                short_name=short_name,
                client_id=client_id,
                days_back=days_back,
                currency=currency,
                salary_unit=salary_unit,
                semantic_zero_attempts=semantic_zero_attempts,
                prior_nonzero_total=prior_nonzero_total,
            )
        except _SnapshotChanged as exc:
            if exc.expected_total is not None and exc.expected_total > 0:
                prior_nonzero_total = exc.expected_total
            if attempt >= snapshot_attempts:
                raise
            await asyncio.sleep(_SNAPSHOT_RETRY_DELAY * attempt)
    raise AssertionError("unreachable")
