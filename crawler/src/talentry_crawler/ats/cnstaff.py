"""CNStaff — GET https://{tenant}.cnstaff.com/recruit?n=1&p={page}."""

from __future__ import annotations

import html
import math
import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_PAGE_SIZE = 15
_MAX_JOBS = 50_000
_JOB_ID_RE = re.compile(r"^[0-9]+$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def origin_from_url(board_url: str) -> str | None:
    try:
        parsed = urlparse(board_url)
        port = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or host == "cnstaff.com"
        or not host.endswith(".cnstaff.com")
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.path.rstrip("/") != "/recruit"
        or parsed.query
        or parsed.fragment
    ):
        return None
    return f"https://{host}"


def _board_url(origin: str) -> str:
    return f"{origin}/recruit"


def _job_url(origin: str, job_id: str) -> str:
    return f"{origin}/recruitment/job/detail/id/{job_id}/"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _html_text(value: object) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    if "<" in cleaned and ">" in cleaned:
        return cleaned
    escaped = html.escape(cleaned).replace("\n", "<br>")
    return f"<p>{escaped}</p>"


def _date(value: object) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    candidate = cleaned.split(" ", 1)[0]
    if candidate == "0000-00-00" or _DATE_RE.fullmatch(candidate) is None:
        return None
    return candidate


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"CNStaff returned invalid {field}")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise ValueError(f"CNStaff returned invalid {field}")
    if parsed < 0:
        raise ValueError(f"CNStaff returned invalid {field}")
    return parsed


def _parse_job(raw: dict, origin: str) -> Job | None:
    job_id = _clean_text(raw.get("job_id"))
    title = _clean_text(raw.get("job_name_show")) or _clean_text(raw.get("job_name"))
    if job_id is None or _JOB_ID_RE.fullmatch(job_id) is None or title is None:
        return None

    responsibilities = _html_text(raw.get("job_detail"))
    qualifications = _html_text(raw.get("job_desc2"))
    sections: list[str] = []
    if responsibilities:
        sections.extend(("<h3>Responsibilities</h3>", responsibilities))
    if qualifications:
        sections.extend(("<h3>Qualifications</h3>", qualifications))
    description = "\n".join(sections) or None

    location = _clean_text(raw.get("job_address_name"))
    metadata = {
        key: value
        for key, value in {
            "id": job_id,
            "employer": _clean_text(raw.get("company_orgnize_name_show")),
            "department": _clean_text(raw.get("ws_system_job_type_ids_name")),
            "job_function": _clean_text(raw.get("g_job_type")),
            "valid_through": _date(raw.get("job_end_at")),
        }.items()
        if value not in (None, "")
    }

    return Job(
        url=_job_url(origin, job_id),
        title=title,
        description=description,
        locations=[location] if location else None,
        date_posted=_date(raw.get("job_published_at")),
        metadata=metadata or None,
    )


async def _fetch_page(origin: str, page: int, client: httpx.AsyncClient) -> dict:
    response = await client.get(
        _board_url(origin),
        params={"n": 1, "p": page},
        headers={
            "accept": "application/json, text/javascript, */*; q=0.01",
            "referer": _board_url(origin),
            "x-requested-with": "XMLHttpRequest",
        },
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(f"CNStaff board {origin!r} returned {response.status_code} (board gone)")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("CNStaff response must be an object")
    return payload


def _parse_page(payload: dict, requested_page: int) -> tuple[int, int, list[dict]]:
    total = _nonnegative_int(payload.get("total"), "total")
    page_meta = payload.get("page")
    rows = payload.get("list")
    if not isinstance(page_meta, dict) or not isinstance(rows, list):
        raise ValueError("CNStaff response omitted page or list")

    current = _nonnegative_int(page_meta.get("now"), "page.now")
    total_pages = _nonnegative_int(page_meta.get("total"), "page.total")
    expected_pages = math.ceil(total / _PAGE_SIZE) if total else 0
    if current != requested_page:
        raise ValueError(f"CNStaff returned page {current}, requested {requested_page}")
    if total_pages != expected_pages:
        raise ValueError(f"CNStaff reported {total_pages} pages for {total} jobs")

    expected_rows = min(_PAGE_SIZE, max(0, total - (requested_page - 1) * _PAGE_SIZE))
    if len(rows) != expected_rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(
            f"CNStaff page {requested_page} returned {len(rows)} rows, expected {expected_rows}"
        )
    return total, total_pages, rows


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    origin = origin_from_url(board.board_url)
    if origin is None:
        raise ValueError(f"Unsupported CNStaff board URL: {board.board_url!r}")

    first_payload = await _fetch_page(origin, 1, client)
    total, total_pages, rows = _parse_page(first_payload, requested_page=1)
    target = min(total, _MAX_JOBS)
    pages = math.ceil(target / _PAGE_SIZE) if target else 0
    rows = rows[:target]

    for page in range(2, pages + 1):
        payload = await _fetch_page(origin, page, client)
        page_total, page_count, page_rows = _parse_page(payload, requested_page=page)
        if page_total != total or page_count != total_pages:
            raise ValueError("CNStaff inventory changed during pagination")
        rows.extend(page_rows[: max(0, target - len(rows))])

    jobs: list[Job] = []
    seen_ids: set[str] = set()
    for row in rows:
        job = _parse_job(row, origin)
        if job is None:
            continue
        job_id = str((job.metadata or {}).get("id"))
        if job_id in seen_ids:
            raise ValueError(f"CNStaff repeated job {job_id}")
        seen_ids.add(job_id)
        jobs.append(job)
    return jobs
