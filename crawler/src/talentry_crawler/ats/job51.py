"""51job — public CoAPI listing and detail responses for employer microsites."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import math
import re
from urllib.parse import urlencode, urlparse

import httpx

from talentry_crawler.models import Board, Job

_PAGE_SIZE = 20
_MAX_JOBS = 50_000
_DETAIL_CONCURRENCY = 5
_API_ORIGIN = "https://coapi.51job.com"
_PUBLIC_SIGNING_KEY = "tuD&#mheJQBlgy&Sm300l8xK^X4NzFYBcrN8@YLCret$fv1AZbtujg*KN^$YnUkh"
_SIGNING_KEY_INDEX = 1
_BOARD_PATH_RE = re.compile(r"/(?:[A-Za-z0-9_-]{1,64}job_list|[A-Za-z0-9_-]{1,64}/job)\.html")
_CAMPUS_ABOUT_BOARD_PATH_RE = re.compile(r"/[A-Za-z0-9_-]{1,64}/about1\.html")
_CTMID_RE = re.compile(r"\bctmid\s*:\s*['\"]?(\d{1,12})")
_JOB_ID_RE = re.compile(r"^[0-9]{1,20}$")
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_QUALIFICATIONS_RE = re.compile(r"(?:岗位要求|任职要求|职位要求)\s*[:：]?", re.IGNORECASE)
_EDGE_BREAKS_RE = re.compile(r"^(?:<br\s*/?>)+|(?:<br\s*/?>)+$", re.IGNORECASE)


def _clean_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _html_fragment(value: object) -> str | None:
    cleaned = _clean_string(value)
    if cleaned is None:
        return None
    if "<" in cleaned and ">" in cleaned:
        return cleaned
    return f"<p>{html.escape(cleaned).replace(chr(10), '<br>')}</p>"


def _board_origin(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host.endswith(".51job.com")
        or host in {"51job.com", "www.51job.com", "jobs.51job.com", "coapi.51job.com"}
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or (
            _BOARD_PATH_RE.fullmatch(parsed.path) is None
            and not (
                host == "campus.51job.com"
                and _CAMPUS_ABOUT_BOARD_PATH_RE.fullmatch(parsed.path)
            )
        )
        or parsed.query
        or parsed.fragment
    ):
        return None
    return f"https://{host}"


def _configured_ctmid(board: Board) -> int | None:
    raw = board.monitor_config.get("ctmid")
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise ValueError("51job ctmid must be a positive integer")
    if isinstance(raw, int):
        ctmid = raw
    elif isinstance(raw, str) and raw.isdigit():
        ctmid = int(raw)
    else:
        raise ValueError("51job ctmid must be a positive integer")
    if ctmid <= 0 or ctmid > 999_999_999_999:
        raise ValueError("51job ctmid must be a positive integer")
    return ctmid


def _ctmid_from_html(page: str) -> int:
    match = _CTMID_RE.search(page)
    if match is None:
        raise ValueError("51job board omitted its public ctmid")
    return int(match.group(1))


def _signed_url(endpoint: str, params: dict) -> str:
    serialized = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    key_slice = _PUBLIC_SIGNING_KEY[_SIGNING_KEY_INDEX : _SIGNING_KEY_INDEX + 15]
    signature = hashlib.md5(
        f"coapi{serialized}{key_slice}".encode()
    ).hexdigest()
    query = urlencode({"key": _SIGNING_KEY_INDEX, "sign": signature, "params": serialized})
    return f"{_API_ORIGIN}/{endpoint}?{query}"


def _parse_jsonp(text: str) -> dict:
    prefix = "jsoncallback("
    if not text.startswith(prefix) or not text.endswith(")"):
        raise ValueError("51job CoAPI returned malformed JSONP")
    try:
        payload = json.loads(text[len(prefix) : -1])
    except json.JSONDecodeError as exc:
        raise ValueError("51job CoAPI returned invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("status") != "1":
        raise ValueError("51job CoAPI reported an unsuccessful response")
    body = payload.get("resultbody")
    if not isinstance(body, dict):
        raise ValueError("51job CoAPI omitted resultbody")
    return body


async def _fetch_jsonp(endpoint: str, params: dict, client: httpx.AsyncClient) -> dict:
    url = _signed_url(endpoint, params)
    response = await client.get(url, follow_redirects=True)
    if response.status_code in {404, 410}:
        raise LookupError("51job public CoAPI endpoint is gone")
    response.raise_for_status()
    return _parse_jsonp(response.text)


async def _resolve_ctmid(board: Board, client: httpx.AsyncClient) -> int:
    configured = _configured_ctmid(board)
    if configured is not None:
        return configured
    response = await client.get(board.board_url, follow_redirects=True)
    if response.status_code in {404, 410}:
        raise LookupError(f"51job board {board.board_url!r} is gone")
    response.raise_for_status()
    return _ctmid_from_html(response.text)


def _list_params(ctmid: int, page: int) -> dict:
    return {
        "ctmid": ctmid,
        "pagesize": _PAGE_SIZE,
        "pagenum": page,
        "jobarea": "",
        "issuedate": "",
        "keyword": "",
        "divid": "",
        "poscode": "",
    }


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"51job returned invalid {field}")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise ValueError(f"51job returned invalid {field}")
    if parsed < 0:
        raise ValueError(f"51job returned invalid {field}")
    return parsed


def _parse_list_page(body: dict, *, requested_page: int) -> tuple[int, list[dict]]:
    total = _nonnegative_int(body.get("totalnum"), "totalnum")
    rows = body.get("joblist")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("51job listing omitted joblist")
    expected = min(_PAGE_SIZE, max(0, total - (requested_page - 1) * _PAGE_SIZE))
    if len(rows) != expected:
        raise ValueError(
            f"51job page {requested_page} returned {len(rows)} rows, expected {expected}"
        )
    return total, rows


def _job_url(job_id: str) -> str:
    return f"https://jobs.51job.com/all/{job_id}.html"


def _date(value: object) -> str | None:
    raw = _clean_string(value)
    if raw is None:
        return None
    match = _DATE_RE.match(raw)
    return match.group(1) if match else None


def _description_parts(raw_html: str) -> tuple[str | None, str | None]:
    def normalized_part(value: str) -> str | None:
        normalized = _html_fragment(value)
        if normalized is None:
            return None
        cleaned = _EDGE_BREAKS_RE.sub("", normalized).strip()
        return cleaned or None

    match = _QUALIFICATIONS_RE.search(raw_html)
    if match is None:
        return normalized_part(raw_html), None
    responsibilities = normalized_part(raw_html[: match.start()])
    qualifications = normalized_part(raw_html[match.end() :])
    return responsibilities, qualifications


def _parse_job(raw: dict, *, ctmid: int, expected_job_id: str) -> Job:
    job_id = _clean_string(raw.get("jobid"))
    title = _clean_string(raw.get("jobname"))
    returned_ctmid = _nonnegative_int(raw.get("ctmid"), "ctmid")
    if (
        job_id is None
        or _JOB_ID_RE.fullmatch(job_id) is None
        or job_id != expected_job_id
        or returned_ctmid != ctmid
        or title is None
    ):
        raise ValueError("51job returned a detail with an invalid identity or title")

    raw_description = _clean_string(raw.get("jobinfo"))
    description = _html_fragment(raw_description)
    if raw_description is None or description is None:
        raise ValueError("51job returned a job without a description")
    responsibilities, qualifications = _description_parts(raw_description)

    location = _clean_string(raw.get("jobareaname")) or _clean_string(raw.get("workareaname"))
    skills_text = _clean_string(raw.get("jkeyword"))
    metadata = {
        key: value
        for key, value in {
            "id": job_id,
            "employer": _clean_string(raw.get("coname")),
            "department": _clean_string(raw.get("divname")),
            "address": _clean_string(raw.get("address")),
            "job_function": _clean_string(raw.get("funtype")),
            "experience": _clean_string(raw.get("workyearname")),
            "education": _clean_string(raw.get("degreefrom")),
            "salary_label": _clean_string(raw.get("providesalarname")),
            "benefits": _clean_string(raw.get("jobwelf")),
            "skills": list(dict.fromkeys(skills_text.split())) if skills_text else None,
            "responsibilities": responsibilities,
            "qualifications": qualifications,
        }.items()
        if value
    }
    return Job(
        url=_job_url(job_id),
        title=title,
        description=description,
        locations=[location] if location else None,
        employment_type=_clean_string(raw.get("term")),
        date_posted=_date(raw.get("issuedate")),
        metadata=metadata or None,
    )


async def _discover(ctmid: int, client: httpx.AsyncClient) -> tuple[list[Job], bool]:
    first_body = await _fetch_jsonp("job_list.php", _list_params(ctmid, 1), client)
    total, first_rows = _parse_list_page(first_body, requested_page=1)
    target = min(total, _MAX_JOBS)
    pages = math.ceil(target / _PAGE_SIZE) if target else 0
    rows = list(first_rows[:target])

    for page in range(2, pages + 1):
        body = await _fetch_jsonp("job_list.php", _list_params(ctmid, page), client)
        page_total, page_rows = _parse_list_page(body, requested_page=page)
        if page_total != total:
            raise ValueError("51job inventory changed during pagination")
        rows.extend(page_rows[: max(0, target - len(rows))])

    job_ids: list[str] = []
    seen_ids: set[str] = set()
    for row in rows:
        job_id = _clean_string(row.get("jobid"))
        if job_id is None or _JOB_ID_RE.fullmatch(job_id) is None:
            raise ValueError("51job listing returned an invalid job ID")
        if job_id in seen_ids:
            raise ValueError(f"51job listing repeated job {job_id}")
        seen_ids.add(job_id)
        job_ids.append(job_id)
    if len(job_ids) != target:
        raise ValueError(f"51job discovered {len(job_ids)} jobs, expected {target}")

    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def fetch_detail(job_id: str) -> Job:
        async with semaphore:
            body = await _fetch_jsonp("job_detail.php", {"jobid": job_id}, client)
        return _parse_job(body, ctmid=ctmid, expected_job_id=job_id)

    jobs = list(await asyncio.gather(*(fetch_detail(job_id) for job_id in job_ids)))
    return jobs, total > _MAX_JOBS


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    origin = _board_origin(board.board_url)
    if origin is None:
        raise ValueError(f"Unsupported 51job board URL: {board.board_url!r}")
    ctmid = await _resolve_ctmid(board, client)
    jobs, truncated = await _discover(ctmid, client)
    return jobs[:_MAX_JOBS] if truncated else jobs
