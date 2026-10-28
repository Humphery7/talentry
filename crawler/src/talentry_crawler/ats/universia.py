"""Universia — branded-board config + public job-posting APIs."""

from __future__ import annotations

import math
import re
from urllib.parse import parse_qsl, urlparse

import httpx

from talentry_crawler.models import Board, Job

_API_ORIGIN = "https://api-manager.universia.net"
_LISTING_URL = f"{_API_ORIGIN}/orientacion-job-posting/v1/api/job-posting"
_BOARD_HOST = "jobboard.universia.net"
_PAGE_SIZE = 100
_MAX_JOBS = 50_000
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,126}[a-z0-9]$|^[a-z0-9]$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_WORKPLACE_TYPES = {
    "remote": "remote",
    "telecommute": "remote",
    "hybrid": "hybrid",
    "onsite": "onsite",
    "on-site": "onsite",
}


def slug_from_url(board_url: str) -> str | None:
    try:
        parsed = urlparse(board_url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != _BOARD_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        return None
    slug = parsed.path.strip("/").lower()
    return slug if _SLUG_RE.fullmatch(slug) else None


def _config_url(slug: str) -> str:
    return f"{_API_ORIGIN}/empleo/entities/v2/jobboard/slug/{slug}/config/"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Universia response contains invalid {field}")
    return value


async def _resolve_board(
    client: httpx.AsyncClient, slug: str
) -> tuple[str, str | None]:
    response = await client.get(
        _config_url(slug),
        params={"status": "published"},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    if response.status_code in {404, 410}:
        raise LookupError(f"Universia board {slug!r} returned {response.status_code} (board gone)")
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict) or payload.get("slug") != slug:
        raise ValueError("Universia configuration returned a mismatched board slug")
    entity = payload.get("entity")
    board_id = entity.get("id") if isinstance(entity, dict) else None
    if not isinstance(board_id, str) or _UUID_RE.fullmatch(board_id) is None:
        raise ValueError("Universia configuration omitted a valid entity UUID")
    if entity.get("entityType") not in {"company", "university"}:
        raise ValueError("Universia configuration returned an unsupported entity type")

    language = None
    languages = payload.get("languages")
    if isinstance(languages, list) and languages:
        candidate = languages[0]
        if isinstance(candidate, str) and re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", candidate):
            language = candidate[:2]
    return board_id.lower(), language


async def _fetch_page(
    client: httpx.AsyncClient, board_id: str, offset: int
) -> dict:
    response = await client.get(
        _LISTING_URL,
        params={
            "offset": offset,
            "limit": _PAGE_SIZE,
            "filterAddressCountry": "false",
            "postingType": ["job", "internship"],
            "dateFrom": "",
            "boards": board_id,
        },
        headers={"Accept": "application/json"},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError("Universia listing returned board gone")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Universia listing response must be an object")
    return payload


def _parse_page(
    payload: dict, board_id: str, requested_offset: int
) -> tuple[list[dict], int]:
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise ValueError("Universia listing response omitted results")
    offset = _nonnegative_int(payload.get("offset"), "offset")
    limit = _nonnegative_int(payload.get("limit"), "limit")
    size = _nonnegative_int(payload.get("size"), "size")
    total = _nonnegative_int(payload.get("total"), "total")
    total_pages = _nonnegative_int(payload.get("totalPages"), "totalPages")
    if offset != requested_offset or limit != _PAGE_SIZE or size != len(rows):
        raise ValueError("Universia listing pagination does not match the request")
    if total_pages != math.ceil(total / _PAGE_SIZE):
        raise ValueError("Universia listing totalPages does not match total")
    expected = min(_PAGE_SIZE, max(0, total - requested_offset))
    if len(rows) != expected:
        raise ValueError(
            f"Universia listing at offset {requested_offset} returned {len(rows)} rows, "
            f"expected {expected}"
        )

    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Universia listing contains a non-object job")
        job_id = row.get("identifier")
        boards = row.get("boards")
        if (
            not isinstance(job_id, str)
            or _UUID_RE.fullmatch(job_id) is None
            or not isinstance(boards, list)
            or board_id not in {str(item).lower() for item in boards}
            or row.get("status") != "published"
        ):
            raise ValueError("Universia listing contains an invalid board-scoped identity")
        if job_id.lower() in seen:
            raise ValueError("Universia listing page contains duplicate job identities")
        seen.add(job_id.lower())
    return rows, total


async def _fetch_all(client: httpx.AsyncClient, board_id: str) -> list[dict]:
    first_payload = await _fetch_page(client, board_id, 0)
    first, total = _parse_page(first_payload, board_id, requested_offset=0)
    target = min(total, _MAX_JOBS)
    rows = first[:target]
    seen = {str(row["identifier"]).lower() for row in rows}

    for offset in range(_PAGE_SIZE, target, _PAGE_SIZE):
        payload = await _fetch_page(client, board_id, offset)
        page, page_total = _parse_page(payload, board_id, requested_offset=offset)
        if page_total != total:
            raise ValueError("Universia listing total changed during pagination")
        page_ids = {str(row["identifier"]).lower() for row in page}
        if seen & page_ids:
            raise ValueError("Universia listing repeated jobs across pages")
        rows.extend(page[: max(0, target - len(rows))])
        seen.update(page_ids)

    if len(rows) != target:
        raise ValueError(f"Universia discovered {len(rows)} jobs, expected {target}")
    return rows


def _locations(row: dict) -> list[str] | None:
    location = row.get("jobLocation")
    address = location.get("address") if isinstance(location, dict) else None
    if not isinstance(address, dict):
        return None
    street = _clean_text(address.get("streetAddress"))
    if street:
        return [street]
    values: list[str] = []
    for key in ("addressLocality", "addressRegion", "addressCountry"):
        value = _clean_text(address.get(key))
        if value and value not in values:
            values.append(value)
    return [", ".join(values)] if values else None


def _job_url(value: object, job_id: str, board_id: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Universia job {job_id} omitted its public URL")
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Universia job {job_id} returned an invalid public URL") from exc
    path = re.fullmatch(
        rf"/[a-z]{{2}}/empleo/{re.escape(job_id)}/[a-z0-9][a-z0-9-]*\.html",
        parsed.path,
        re.IGNORECASE,
    )
    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    query = dict(query_items)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "www.universia.net"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or path is None
        or parsed.fragment
        or len(query_items) != len(query)
        or query.get("referer", "").lower() != board_id
        or any(key not in {"referer", "entityid"} for key in query)
        or ("entityid" in query and query["entityid"].lower() != board_id)
    ):
        raise ValueError(f"Universia job {job_id} returned an untrusted public URL")
    return value


def _description(row: dict, job_id: str) -> tuple[str, dict]:
    main = row.get("description")
    if not isinstance(main, str) or not main.strip():
        raise ValueError(f"Universia job {job_id} omitted its description")
    sections = [main.strip()]
    extras: dict[str, str] = {}
    requirements = row.get("requirements")
    if isinstance(requirements, str) and requirements.strip():
        sections.extend(["<h3>Requirements</h3>", requirements.strip()])
        extras["qualifications"] = requirements.strip()
    education = row.get("incentiveCompensation")
    if isinstance(education, str) and education.strip():
        sections.extend(["<h3>Education</h3>", education.strip()])
        extras["qualifications"] = "".join(
            part for part in (extras.get("qualifications"), education.strip()) if part
        )
    valid_through = _clean_text(row.get("validThrough"))
    if valid_through:
        extras["valid_through"] = valid_through
    return "\n".join(sections), extras


def _parse_job(row: dict, board_id: str, language: str | None) -> Job:
    job_id = str(row.get("identifier", "")).lower()
    title = _clean_text(row.get("title"))
    if not title:
        raise ValueError(f"Universia job {job_id} omitted its title")
    description, extras = _description(row, job_id)

    metadata: dict[str, object] = {
        "universia_job_id": job_id,
        "universia_board_id": board_id,
    }
    for source, target in (
        ("postingType", "posting_type"),
        ("educationalLevel", "educational_level"),
        ("totalJobOpenings", "total_job_openings"),
    ):
        if row.get(source) is not None:
            metadata[target] = row[source]
    role = row.get("role")
    if isinstance(role, dict) and (role_name := _clean_text(role.get("name"))):
        metadata["role"] = role_name
    contract = row.get("contractType")
    if isinstance(contract, dict) and (contract_name := _clean_text(contract.get("name"))):
        metadata["contract_type"] = contract_name
    metadata.update(extras)
    metadata["language"] = language

    raw_workplace = _clean_text(row.get("jobLocationType"))
    workplace_type = (
        _WORKPLACE_TYPES.get(raw_workplace.casefold()) if raw_workplace else None
    )

    return Job(
        url=_job_url(row.get("url"), job_id, board_id),
        title=title,
        description=description,
        locations=_locations(row),
        employment_type=_clean_text(row.get("employmentType")),
        workplace_type=workplace_type,
        date_posted=_clean_text(row.get("datePosted")),
        metadata={key: value for key, value in metadata.items() if value not in (None, "")},
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"Unsupported Universia board URL: {board.board_url!r}")

    board_id, detected_language = await _resolve_board(client, slug)
    configured_id = board.monitor_config.get("board_id")
    if configured_id is not None and str(configured_id).lower() != board_id:
        raise ValueError("Universia configured board_id no longer matches the public board")
    language = board.monitor_config.get("language") or detected_language
    if not isinstance(language, str) or re.fullmatch(r"[a-z]{2}", language) is None:
        language = detected_language

    rows = await _fetch_all(client, board_id)
    return [_parse_job(row, board_id=board_id, language=language) for row in rows]
