"""NowHiring — career-site config, job search, and per-job details."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, urlparse

import httpx

from talentry_crawler.models import Board, Job

_HOST = "nowhiring.com"
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}", re.IGNORECASE)
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
_DETAIL_CONCURRENCY = 10
_MAX_JOBS = 50_000


def slug_from_url(board_url: str) -> str | None:
    try:
        parsed = urlparse(board_url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != _HOST
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 1 or not _SLUG_RE.fullmatch(parts[0]):
        return None
    return parts[0].lower()


def _site_url(slug: str) -> str:
    key = quote(f"{_HOST}/{slug}", safe="")
    return f"https://{_HOST}/api/career-live-sites/{key}"


def _values_by_field(criteria: object) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    if not isinstance(criteria, list):
        return values
    for item in criteria:
        if not isinstance(item, dict):
            continue
        name = item.get("fieldName")
        value = item.get("fieldValue")
        if isinstance(name, str) and isinstance(value, (str, int)) and str(value).strip():
            values.setdefault(name, []).append(str(value).strip())
    return values


async def _fetch_site(slug: str, client: httpx.AsyncClient) -> dict:
    response = await client.get(
        _site_url(slug),
        headers={"Accept": "application/json", "Referer": f"https://{_HOST}/{slug}/"},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(f"NowHiring board {slug!r} returned {response.status_code}")
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("NowHiring career-site response must be an object")
    values = _values_by_field(payload.get("jobSearchCriteria"))
    customer_ids = values.get("billingAccountId", [])
    if not customer_ids:
        raise ValueError("NowHiring career site omitted its billing account scope")
    return {
        "slug": slug,
        "customer_ids": customer_ids,
        "brand_template_ids": values.get("brandTemplateId", []),
        "brand_ids": values.get("brandId", []),
    }


def _search_payload(site: dict, start: int) -> dict:
    return {
        "customerId": list(site["customer_ids"]),
        "brandTemplateId": list(site["brand_template_ids"]),
        "brandId": list(site["brand_ids"]),
        "start": str(start),
        "sort": "jobtitle",
        "includefacetlist": False,
        "manyselectfacets": [],
        "specificfacets": [],
        "disablesuppression": True,
        "specificlocationsonly": True,
    }


async def _fetch_search_page(
    site: dict, start: int, client: httpx.AsyncClient
) -> tuple[list[dict], int]:
    response = await client.post(
        f"https://{_HOST}/api/jobs/search",
        json=_search_payload(site, start),
        headers={"Accept": "application/json", "Referer": f"https://{_HOST}/"},
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("list") if isinstance(payload, dict) else None
    total = payload.get("total") if isinstance(payload, dict) else None
    if (
        not isinstance(rows, list)
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
    ):
        raise ValueError("NowHiring job search returned an invalid list or total")
    return [item for item in rows if isinstance(item, dict)], total


async def _fetch_detail(job_id: str, client: httpx.AsyncClient) -> dict:
    response = await client.get(
        f"https://{_HOST}/api/jobs/{job_id}",
        headers={"Accept": "application/json", "Referer": f"https://{_HOST}/"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"NowHiring job {job_id!r} detail must be an object")
    return payload


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _locations(raw: dict) -> list[str] | None:
    parts: list[str] = []
    for key in ("addressLine1", "addressLine2", "city", "stateProvCode", "postalCode"):
        value = _clean_text(raw.get(key))
        if value and value not in parts:
            parts.append(value)
    return [", ".join(parts)] if parts else None


def _parse_job(raw: dict, slug: str, customer_id: str) -> Job | None:
    job_id = _clean_text(raw.get("id"))
    detail_customer_id = _clean_text(raw.get("billingAccountId")) or customer_id
    title = _clean_text(raw.get("jobTitle"))
    if (
        job_id is None
        or _ID_RE.fullmatch(job_id) is None
        or not detail_customer_id.isdigit()
        or title is None
    ):
        return None

    categories = raw.get("categories")
    employment_type = None
    if isinstance(categories, list):
        employment_type = next(
            (value for item in categories if (value := _clean_text(item)) is not None),
            None,
        )

    metadata = {
        key: value
        for key, value in {
            "job_id": raw.get("id"),
            "company": raw.get("company"),
            "application_url": raw.get("thirdPartyApplyUrl") or raw.get("applicationURL"),
            "brand_id": raw.get("brandId"),
        }.items()
        if value not in (None, "")
    }

    return Job(
        url=f"https://{_HOST}/{slug}/job-details/{job_id}",
        title=title,
        description=_clean_text(raw.get("jobDescription")),
        locations=_locations(raw),
        employment_type=employment_type,
        date_posted=_clean_text(raw.get("postedDate")),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"Cannot derive a valid NowHiring career-site slug from {board.board_url!r}")
    slug = slug.lower()
    site = await _fetch_site(slug, client)

    summaries: list[dict] = []
    total = 0
    while len(summaries) < _MAX_JOBS:
        page, total = await _fetch_search_page(site, len(summaries), client)
        if not page:
            if len(summaries) < total:
                raise ValueError("NowHiring search stopped before its advertised total")
            break
        summaries.extend(page)
        if len(summaries) >= total:
            break

    ids: list[str] = []
    seen_ids: set[str] = set()
    for summary in summaries:
        job_id = _clean_text(summary.get("id"))
        if job_id is None or _ID_RE.fullmatch(job_id) is None:
            raise ValueError("NowHiring search returned a job without a valid id")
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)
        ids.append(job_id)

    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def hydrate(job_id: str) -> dict:
        async with semaphore:
            return await _fetch_detail(job_id, client)

    details = await asyncio.gather(*(hydrate(job_id) for job_id in ids))
    customer_id = str(site["customer_ids"][0])
    jobs = [
        job
        for raw in details
        if (job := _parse_job(raw, slug, customer_id)) is not None
    ]
    if details and not jobs:
        raise ValueError("NowHiring details returned no valid jobs")
    return jobs
