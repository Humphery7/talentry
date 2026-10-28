"""Wecruit (Hotjob) — public recruiting lane and detail APIs."""

from __future__ import annotations

import asyncio
import html
import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_PAGE_SIZE = 50
_MAX_JOBS = 50_000
_DETAIL_CONCURRENCY = 20
_RECRUIT_TYPES = (1, 2, 12, 13)
_SUITE_RE = re.compile(r"^/SU(?P<suite>[0-9a-f]{24})/(?:pb|mc)(?:/|$)", re.IGNORECASE)
_SUITE_VALUE_RE = re.compile(r"^[0-9a-f]{24}$", re.IGNORECASE)
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:$|[ T])")
_HEADERS = {"content-type": "application/x-www-form-urlencoded"}


def _origin(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return None
    return f"https://{parsed.netloc.casefold()}"


def _suite_from_url(url: str) -> str | None:
    try:
        path = urlparse(url).path
    except ValueError:
        return None
    match = _SUITE_RE.match(path)
    return match.group("suite").casefold() if match else None


def _envelope(payload: dict, context: str) -> dict:
    data = payload.get("data")
    if str(payload.get("state")) != "200" or not isinstance(data, dict):
        raise ValueError(f"Wecruit {context} response has an invalid envelope")
    return data


async def _post_json(
    client: httpx.AsyncClient,
    url: str,
    data: dict[str, object],
    *,
    context: str,
) -> dict:
    response = await client.post(
        url,
        data=data,
        headers=_HEADERS,
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Wecruit {context} response is invalid")
    return payload


async def _resolve_tenant(
    board: Board,
    client: httpx.AsyncClient,
) -> tuple[str, str]:
    metadata = board.monitor_config
    origin = metadata.get("api_origin")
    suite_key = metadata.get("suite_key")
    if origin is not None and (not isinstance(origin, str) or _origin(origin) != origin):
        raise ValueError("Wecruit api_origin must be a canonical HTTPS origin")
    if suite_key is not None and (
        not isinstance(suite_key, str) or _SUITE_VALUE_RE.fullmatch(suite_key) is None
    ):
        raise ValueError("Wecruit suite_key must be a 24-character hexadecimal token")

    board_origin = _origin(board.board_url)
    if board_origin is None:
        raise ValueError(f"Cannot derive Wecruit origin from {board.board_url!r}")
    url_suite = _suite_from_url(board.board_url)

    if suite_key is None and url_suite is None:
        payload = await _post_json(
            client,
            f"{board_origin}/wecruit/common/getSLD",
            {"sld": urlparse(board.board_url).netloc.casefold()},
            context="SLD",
        )
        data = _envelope(payload, "SLD")
        link_data = data.get("linkData")
        link = link_data.get("link") if isinstance(link_data, dict) else None
        if not isinstance(link, str):
            raise ValueError("Wecruit SLD response omitted its suite link")
        link_origin = _origin(link)
        link_suite = _suite_from_url(link)
        if link_origin is None or link_suite is None:
            raise ValueError("Wecruit SLD response has an invalid suite link")
        if link_origin not in {board_origin, "https://wecruit.hotjob.cn"}:
            raise ValueError("Wecruit SLD response points to an unexpected host")
        origin = origin or link_origin
        suite_key = suite_key or link_suite

    suite_key = suite_key or url_suite
    origin = origin or board_origin
    return origin, suite_key.casefold()


async def _listing_page(
    client: httpx.AsyncClient,
    origin: str,
    suite_key: str,
    recruit_type: int,
    page: int,
) -> dict:
    payload = await _post_json(
        client,
        f"{origin}/wecruit/positionInfo/listPosition/SU{suite_key}",
        {
            "isFrompb": "true",
            "recruitType": recruit_type,
            "pageSize": _PAGE_SIZE,
            "currentPage": page,
        },
        context=f"listing lane {recruit_type} page {page}",
    )
    return _envelope(payload, f"listing lane {recruit_type} page {page}")


def _page_form(data: dict, recruit_type: int, page: int) -> tuple[list[dict], int, int]:
    form = data.get("pageForm")
    if not isinstance(form, dict):
        raise ValueError("Wecruit listing response is missing pageForm")
    rows = form.get("pageData")
    total = form.get("dataCount")
    total_pages = form.get("totalPage")
    current_page = form.get("currentPage")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Wecruit listing response has invalid rows")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError("Wecruit listing response has an invalid total")
    if (
        isinstance(total_pages, bool)
        or not isinstance(total_pages, int)
        or total_pages < 0
        or isinstance(current_page, bool)
        or not isinstance(current_page, int)
    ):
        raise ValueError("Wecruit listing response has invalid pagination")
    if total_pages == 0 and total == 0 and not rows and current_page in {0, page}:
        return [], 0, 0
    if current_page != page:
        raise ValueError("Wecruit listing response has an unexpected page number")
    return rows, total, total_pages


def _date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = _DATE_RE.match(value.strip())
    return match.group(1) if match else None


def _text_html(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    lines = [
        html.escape(line.strip(), quote=False)
        for line in value.splitlines()
        if line.strip()
    ]
    return f"<p>{'<br>'.join(lines)}</p>" if lines else None


def _description(detail: dict) -> str | None:
    sections: list[str] = []
    responsibilities = _text_html(detail.get("workContent"))
    qualifications = _text_html(detail.get("serviceCondition"))
    if responsibilities:
        sections.extend(("<h3>工作职责</h3>", responsibilities))
    if qualifications:
        sections.extend(("<h3>任职要求</h3>", qualifications))
    return "\n".join(sections) or None


def _locations(detail: dict) -> list[str] | None:
    raw = detail.get("workPlaceList")
    locations: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            name = item.get("name") if isinstance(item, dict) else None
            if isinstance(name, str) and name.strip() and name.strip() not in locations:
                locations.append(name.strip())
    if not locations:
        fallback = detail.get("workPlaceStr")
        if isinstance(fallback, str) and fallback.strip():
            locations.append(fallback.strip())
    return locations or None


def _parse_job(
    origin: str,
    suite_key: str,
    listing: dict,
    detail: dict,
) -> Job | None:
    post_id = listing.get("postId")
    title = detail.get("postName") or listing.get("postName")
    recruit_type = listing.get("recruitType")
    if not isinstance(post_id, str) or not post_id:
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(recruit_type, int):
        return None

    metadata: dict[str, object] = {"recruit_type": recruit_type}
    for source, target in (
        ("postCode", "post_code"),
        ("externalPostId", "external_post_id"),
        ("company", "company"),
        ("department", "department"),
        ("postTypeName", "post_type"),
        ("jobLevel", "job_level"),
        ("education", "education"),
        ("recruitNumStr", "recruits"),
        ("projectName", "project"),
    ):
        value = detail.get(source)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and value != "":
            metadata[target] = value

    return Job(
        url=(
            f"{origin}/SU{suite_key}/pb/posDetail.html?"
            f"postId={post_id}&postType={recruit_type}"
        ),
        title=title.strip(),
        description=_description(detail),
        locations=_locations(detail),
        date_posted=_date(detail.get("publishDate") or listing.get("publishDate")),
        metadata=metadata,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    origin, suite_key = await _resolve_tenant(board, client)
    configured_types = board.monitor_config.get("recruit_types", list(_RECRUIT_TYPES))
    if (
        not isinstance(configured_types, list)
        or not configured_types
        or any(type(value) is not int or value not in _RECRUIT_TYPES for value in configured_types)
        or len(set(configured_types)) != len(configured_types)
    ):
        raise ValueError(f"Wecruit recruit_types must be unique values from {_RECRUIT_TYPES}")

    listings: list[dict] = []
    for recruit_type in configured_types:
        first = await _listing_page(client, origin, suite_key, recruit_type, 1)
        rows, total, total_pages = _page_form(first, recruit_type, 1)
        listings.extend(rows)
        for page in range(2, total_pages + 1):
            data = await _listing_page(client, origin, suite_key, recruit_type, page)
            page_rows, page_total, page_pages = _page_form(data, recruit_type, page)
            if page_total != total or page_pages != total_pages:
                raise ValueError("Wecruit listing changed during pagination")
            listings.extend(page_rows)
        if len(listings) >= _MAX_JOBS:
            break

    listings = listings[:_MAX_JOBS]
    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def fetch_detail(listing: dict) -> dict | None:
        post_id = listing.get("postId")
        if not isinstance(post_id, str):
            return None
        async with semaphore:
            payload = await _post_json(
                client,
                f"{origin}/wecruit/positionInfo/listPositionDetail/SU{suite_key}",
                {"postId": post_id},
                context=f"detail {post_id}",
            )
        detail = _envelope(payload, f"detail {post_id}")
        if detail.get("postId") != post_id:
            raise ValueError(f"Wecruit detail identity mismatch for {post_id!r}")
        if detail.get("recruitType") != listing.get("recruitType"):
            raise ValueError(f"Wecruit detail lane mismatch for {post_id!r}")
        return detail

    details = await asyncio.gather(
        *(fetch_detail(listing) for listing in listings),
        return_exceptions=True,
    )

    jobs: list[Job] = []
    seen: set[str] = set()
    for listing, detail in zip(listings, details, strict=True):
        if isinstance(detail, BaseException) or detail is None:
            continue
        job = _parse_job(origin, suite_key, listing, detail)
        if job is None or job.url in seen:
            continue
        seen.add(job.url)
        jobs.append(job)
    return jobs
