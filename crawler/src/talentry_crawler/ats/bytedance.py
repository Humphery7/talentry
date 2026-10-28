"""ByteDance — public careers search APIs for global and China portals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_API_ORIGIN = "https://jobs.bytedance.com"
_SEARCH_API = f"{_API_ORIGIN}/api/v1/search/job/posts"
_GLOBAL_API = f"{_API_ORIGIN}/api/v1/public/supplier/search/job/posts"
_FILTER_API = f"{_API_ORIGIN}/api/v1/config/job/filters/2"
_PAGE_SIZE = 1_000
_RESULT_CAP = 10_000
_MAX_JOBS = 50_000


@dataclass(frozen=True, slots=True)
class _Portal:
    api_url: str
    portal_type: int | None
    website_path: str
    portal_channel: str | None
    detail_template: str
    page_name: str
    partition_categories: bool = False


_GLOBAL = _Portal(
    api_url=_GLOBAL_API,
    portal_type=None,
    website_path="en",
    portal_channel=None,
    detail_template="https://joinbytedance.com/search/{id}",
    page_name="",
)
_EXPERIENCED = _Portal(
    api_url=_SEARCH_API,
    portal_type=2,
    website_path="society",
    portal_channel="office",
    detail_template=f"{_API_ORIGIN}/experienced/position/{{id}}/detail",
    page_name="experienced",
    partition_categories=True,
)
_CAMPUS = _Portal(
    api_url=_SEARCH_API,
    portal_type=3,
    website_path="campus",
    portal_channel="campus",
    detail_template=f"{_API_ORIGIN}/campus/position/{{id}}/detail",
    page_name="campus",
)


def _portal_for_url(url: str) -> _Portal | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    path = parsed.path.rstrip("/")
    if parsed.query or parsed.fragment:
        return None
    if host in {"joinbytedance.com", "www.joinbytedance.com"} and path in {"", "/search"}:
        return _GLOBAL
    if host != "jobs.bytedance.com":
        return None
    if path == "/experienced/position":
        return _EXPERIENCED
    if path == "/campus/position":
        return _CAMPUS
    return None


def _headers(portal: _Portal) -> dict[str, str]:
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
        ),
        "website-path": portal.website_path,
        "portal-platform": "pc",
    }
    if portal.portal_channel:
        headers["portal-channel"] = portal.portal_channel
        headers["origin"] = _API_ORIGIN
        headers["referer"] = f"{_API_ORIGIN}/{portal.page_name}/position"
    if portal is _GLOBAL:
        headers["x-tt-env"] = "boe_epam_api"
    return headers


def _body(portal: _Portal, *, offset: int, category_ids: list[str] | None) -> dict:
    if portal is _GLOBAL:
        return {
            "recruitment_id_list": [],
            "job_category_id_list": category_ids or [],
            "subject_id_list": [],
            "location_code_list": [],
            "keyword": "",
            "limit": _PAGE_SIZE,
            "offset": offset,
        }
    return {
        "keyword": "",
        "limit": _PAGE_SIZE,
        "offset": offset,
        "job_category_id_list": category_ids or [],
        "tag_id_list": [],
        "location_code_list": [],
        "subject_id_list": [],
        "recruitment_id_list": [],
        "portal_type": portal.portal_type,
        "job_function_id_list": [],
        "storefront_id_list": [],
        "portal_entrance": 1,
    }


def _page(data: object) -> tuple[list[dict], int]:
    if not isinstance(data, dict) or data.get("code") != 0:
        raise ValueError("ByteDance jobs API returned an invalid response")
    payload = data.get("data")
    if not isinstance(payload, dict):
        raise ValueError("ByteDance jobs API omitted its data object")
    rows = payload.get("job_post_list")
    total = payload.get("count")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("ByteDance jobs API returned an invalid job list")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError("ByteDance jobs API returned an invalid total")
    return rows, total


async def _fetch_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    body: dict | None = None,
) -> object:
    response = await client.request(method, url, headers=headers, json=body, follow_redirects=True)
    response.raise_for_status()
    return response.json()


async def _collect_partition(
    client: httpx.AsyncClient,
    portal: _Portal,
    category_ids: list[str] | None,
) -> tuple[list[dict], int]:
    headers = _headers(portal)
    items: list[dict] = []
    expected_total: int | None = None
    offset = 0

    while expected_total is None or offset < expected_total:
        data = await _fetch_json(
            client,
            "POST",
            portal.api_url,
            headers,
            _body(portal, offset=offset, category_ids=category_ids),
        )
        rows, total = _page(data)
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise ValueError("ByteDance jobs total changed during pagination")
        if expected_total >= _RESULT_CAP:
            raise ValueError("ByteDance query reached the 10,000-result cap")
        if expected_total == 0:
            if rows:
                raise ValueError("ByteDance jobs API returned rows with a zero total")
            return [], 0
        if not rows:
            raise ValueError(
                f"ByteDance pagination ended at {len(items)} of {expected_total} jobs"
            )
        items.extend(rows)
        offset += _PAGE_SIZE

    ids = [str(item.get("id") or "") for item in items]
    if any(not value for value in ids) or len(set(ids)) != expected_total:
        raise ValueError(
            f"ByteDance pagination produced {len(set(ids))} unique IDs for {expected_total} jobs"
        )
    return items, expected_total


def _category_partitions(data: object) -> list[list[str]]:
    if not isinstance(data, dict) or data.get("code") != 0:
        raise ValueError("ByteDance filters API returned an invalid response")
    payload = data.get("data")
    if not isinstance(payload, dict):
        raise ValueError("ByteDance filters API omitted its data object")
    categories = payload.get("job_type_list")
    counts = payload.get("job_type_count_map")
    if not isinstance(categories, list) or not isinstance(counts, dict) or not categories:
        raise ValueError("ByteDance filters API omitted category partitions")

    partitions: list[list[str]] = []
    for category in categories:
        if not isinstance(category, dict) or not isinstance(category.get("id"), str):
            raise ValueError("ByteDance filters API returned an invalid category")
        category_id = category["id"]
        count = counts.get(category_id)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"ByteDance filters API omitted the count for {category_id}")
        if count == 0:
            continue
        if count < _RESULT_CAP:
            partitions.append([category_id])
            continue
        children = category.get("children")
        if not isinstance(children, list) or not children:
            raise ValueError(f"ByteDance category {category_id} exceeds the result cap")
        for child in children:
            if not isinstance(child, dict) or not isinstance(child.get("id"), str):
                raise ValueError("ByteDance filters API returned an invalid child category")
            partitions.append([child["id"]])
    return partitions


async def _collect(client: httpx.AsyncClient, portal: _Portal) -> list[dict]:
    if not portal.partition_categories:
        items, _total = await _collect_partition(client, portal, None)
        return items

    filters = await _fetch_json(client, "GET", _FILTER_API, _headers(portal))
    partitions = _category_partitions(filters)
    if not partitions:
        return []

    collected: dict[str, dict] = {}
    partition_total = 0
    for category_ids in partitions:
        items, total = await _collect_partition(client, portal, category_ids)
        partition_total += total
        for item in items:
            collected[str(item["id"])] = item
    if len(collected) != partition_total:
        raise ValueError("ByteDance category partitions overlapped")
    if len(collected) > _MAX_JOBS:
        raise ValueError("ByteDance inventory exceeded the safety cap")
    return list(collected.values())


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _to_job(item: dict, portal: _Portal) -> Job | None:
    job_id = str(item.get("id") or "")
    title = _text(item.get("title"))
    if not job_id or not title:
        return None

    responsibility = _text(item.get("description"))
    requirement = _text(item.get("requirement"))
    parts: list[str] = []
    if responsibility:
        parts.extend(("<h3>Responsibilities</h3>", responsibility))
    if requirement:
        parts.extend(("<h3>Requirements</h3>", requirement))

    city_value = item.get("city_info")
    city: dict = city_value if isinstance(city_value, dict) else {}
    parent_value = city.get("parent")
    parent: dict = parent_value if isinstance(parent_value, dict) else {}
    location_parts = [_text(city.get("en_name")), _text(parent.get("en_name"))]
    location = ", ".join(dict.fromkeys(part for part in location_parts if part))

    recruit_value = item.get("recruit_type")
    recruit: dict = recruit_value if isinstance(recruit_value, dict) else {}
    category = item.get("job_category")
    if not isinstance(category, dict):
        category_value = item.get("job_type")
        category = category_value if isinstance(category_value, dict) else {}
    team = _text(category.get("en_name")) or _text(category.get("name"))

    metadata = {"team": team} if team else None
    return Job(
        url=portal.detail_template.format(id=job_id),
        title=title,
        description="".join(parts) or None,
        locations=[location] if location else None,
        employment_type=_text(recruit.get("en_name")) or _text(recruit.get("name")),
        date_posted=str(item["create_time"]) if item.get("create_time") is not None else None,
        metadata=metadata,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    portal = _portal_for_url(board.board_url)
    if portal is None:
        raise ValueError(f"Unsupported ByteDance board URL: {board.board_url!r}")

    raw_jobs = await _collect(client, portal)
    jobs: list[Job] = []
    seen: set[str] = set()
    for raw in raw_jobs:
        job = _to_job(raw, portal)
        if job is None or job.url in seen:
            continue
        seen.add(job.url)
        jobs.append(job)
    return jobs
