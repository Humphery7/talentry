"""Recruiter.co.kr — public jobflex list + per-position detail APIs."""

from __future__ import annotations

import asyncio
import html
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx

from talentry_crawler.models import Board, Job

_API_BASE = "https://api-recruiter.recruiter.co.kr"
_LIST_PATH = "/position/v1/jobflex"
_DETAIL_PATH = "/position/v2/jobflex/{position_sn}"
_PAGE_SIZE = 100
_MAX_JOBS = 20_000
_DETAIL_CONCURRENCY = 8
_SOURCE_TZ = ZoneInfo("Asia/Seoul")
_UTC = ZoneInfo("UTC")
_IGNORE_SLUGS = frozenset({"www", "api", "api-recruiter", "infra1-static", "cdn"})


def slug_from_url(board_url: str) -> str | None:
    host = (urlparse(board_url).hostname or "").lower()
    if not host.endswith(".recruiter.co.kr"):
        return None
    slug = host.removesuffix(".recruiter.co.kr")
    if not slug or slug in _IGNORE_SLUGS or "." in slug:
        return None
    return slug


def _headers(slug: str) -> dict[str, str]:
    return {
        "prefix": f"{slug}.recruiter.co.kr",
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "referer": f"https://{slug}.recruiter.co.kr/",
    }


def _job_url(slug: str, position_sn: object) -> str:
    return f"https://{slug}.recruiter.co.kr/career/jobs/{position_sn}"


def _list_body(page: int, include_closed: bool) -> dict:
    return {
        "pageableRq": {"page": page, "size": _PAGE_SIZE, "sort": ["CREATED_DATE_TIME"]},
        "filter": {
            "keyword": "",
            "tagSnList": [],
            "jobGroupSnList": [],
            "careerTypeList": [],
            "regionSnList": [],
            "submissionStatusList": [] if include_closed else ["IN_SUBMISSION"],
            "openStatusList": [] if include_closed else ["OPEN"],
            "resumeLanguageTypeList": [],
        },
    }


def _date(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if "T" not in raw:
        return raw
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return raw.split("T", 1)[0] or None
    local = parsed.replace(tzinfo=_SOURCE_TZ) if parsed.tzinfo is None else parsed
    return local.astimezone(_UTC).date().isoformat()


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _locations(detail: dict, summary: dict) -> list[str] | None:
    names: list[str] = []
    seen: set[str] = set()

    def push(value: object) -> None:
        if isinstance(value, str):
            name = value.strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        elif isinstance(value, dict):
            for key in ("regionName", "name", "cityName", "siteName", "displayName"):
                nested = value.get(key)
                if isinstance(nested, str) and nested.strip():
                    push(nested)
                    return

    for source in (summary, detail):
        for key in (
            "regionList",
            "regionNameList",
            "workPlace",
            "workPlaceList",
            "workingArea",
            "workingAreaList",
            "siteList",
            "locationList",
        ):
            value = source.get(key)
            if isinstance(value, list):
                for item in value:
                    push(item)
            elif value:
                push(value)
        for key in ("regionName", "workPlaceName", "siteName", "cityName"):
            push(source.get(key))

    return names or None


def _parse_summary(raw: dict, slug: str) -> dict | None:
    position_sn = raw.get("positionSn")
    if position_sn in (None, ""):
        return None
    return {
        "position_sn": position_sn,
        "url": _job_url(slug, position_sn),
        "title": _clean_text(raw.get("title")),
        "start": raw.get("startDateTime"),
        "career_type": _clean_text(raw.get("careerType")),
        "classification": _clean_text(raw.get("classificationCode")),
        "tags": raw.get("tagList") if isinstance(raw.get("tagList"), list) else [],
        "open_status": raw.get("openStatus"),
        "submission_status": raw.get("submissionStatus"),
    }


def _parse_job(detail: dict, summary: dict) -> Job | None:
    title = _clean_text(detail.get("title")) or summary.get("title")
    if not title:
        return None

    description = detail.get("jobDescription")
    if isinstance(description, str) and description.strip():
        if detail.get("jobDescriptionType") not in (None, "HTML"):
            description = f"<pre>{html.escape(description.strip())}</pre>"
        else:
            description = description.strip()
    else:
        description = None

    tags = detail.get("tagList") or summary.get("tags") or []
    tag_names = [
        tag.get("tagName")
        for tag in tags
        if isinstance(tag, dict) and isinstance(tag.get("tagName"), str)
    ] if isinstance(tags, list) else []

    metadata = {
        key: value
        for key, value in {
            "position_sn": summary["position_sn"],
            "classification": _clean_text(detail.get("classificationCode"))
            or summary.get("classification"),
            "tags": tag_names,
            "valid_through": _date(detail.get("endDateTime")),
            "announcement_type": _clean_text(detail.get("announcementType")),
            "recruitment_type": _clean_text(detail.get("recruitmentType")),
        }.items()
        if value not in (None, "", [])
    }

    return Job(
        url=summary["url"],
        title=title,
        description=description,
        locations=_locations(detail, summary),
        employment_type=_clean_text(detail.get("careerType")) or summary.get("career_type"),
        date_posted=_date(detail.get("startDateTime") or summary.get("start")),
        metadata=metadata or None,
    )


async def _fetch_detail(
    slug: str, position_sn: object, client: httpx.AsyncClient
) -> dict | None:
    response = await client.get(
        _API_BASE + _DETAIL_PATH.format(position_sn=position_sn),
        headers=_headers(slug),
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        return None
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else None


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not slug:
        raise ValueError(
            f"Cannot derive Recruiter.co.kr slug from {board.board_url!r} "
            "and no slug in monitor_config"
        )

    include_closed = bool(board.monitor_config.get("include_closed"))
    summaries: list[dict] = []
    page = 1
    total_pages: int | None = None

    while page <= 200 and len(summaries) < _MAX_JOBS:
        response = await client.post(
            _API_BASE + _LIST_PATH,
            headers=_headers(slug),
            json=_list_body(page, include_closed),
        )
        if response.status_code in {400, 404, 410}:
            raise LookupError(
                f"Recruiter.co.kr board {slug!r} returned {response.status_code} (board gone)"
            )
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Recruiter.co.kr list response must be a JSON object")
        items = payload.get("list") or []
        if not isinstance(items, list):
            raise ValueError("Recruiter.co.kr list response must contain a list")

        for raw in items:
            if isinstance(raw, dict):
                parsed = _parse_summary(raw, slug)
                if parsed is not None:
                    summaries.append(parsed)
                    if len(summaries) >= _MAX_JOBS:
                        break

        pagination = payload.get("pagination") or {}
        if total_pages is None:
            raw_pages = pagination.get("totalPages")
            if isinstance(raw_pages, int) and not isinstance(raw_pages, bool):
                total_pages = raw_pages
            else:
                total_count = pagination.get("totalCount")
                if isinstance(total_count, int) and not isinstance(total_count, bool):
                    total_pages = max(1, (total_count + _PAGE_SIZE - 1) // _PAGE_SIZE)

        if not items:
            break
        if total_pages is not None and page >= total_pages:
            break
        page += 1

    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def enrich(summary: dict) -> Job:
        async with semaphore:
            detail = await _fetch_detail(slug, summary["position_sn"], client)
        return _parse_job(detail or {}, summary)

    parsed = await asyncio.gather(*(enrich(summary) for summary in summaries))
    return [job for job in parsed if job is not None]
