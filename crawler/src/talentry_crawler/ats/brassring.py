"""BrassRing / Infinite Talent — direct public search API session."""

from __future__ import annotations

import asyncio
import html
import json
import math
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import httpx

from talentry_crawler.models import Board, Job

_PAGE_SIZE = 50
_MAX_JOBS = 50_000
_BOARD_PATH_RE = re.compile(r"/tgnewui/search/", re.IGNORECASE)
_TOKEN_RE = re.compile(
    r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', re.IGNORECASE
)
_COOKIE_VALUE_RE = re.compile(r'id="CookieValue"[^>]*value="([^"]*)"', re.IGNORECASE)
_DETAIL_CONCURRENCY = 8
_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json; charset=utf-8",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}


class _PreloadParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.value: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "input" or self.value is not None:
            return
        attributes = {key.casefold(): value for key, value in attrs}
        if attributes.get("id") == "preLoadJSON" and attributes.get("value"):
            self.value = attributes["value"]


def _clean_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(html.unescape(value).split())
    return cleaned or None


def _board_ids(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if not _BOARD_PATH_RE.search(parsed.path):
        return None
    query = parse_qs(parsed.query)
    partner_id = (query.get("partnerid") or query.get("partnerId") or [None])[0]
    site_id = (query.get("siteid") or query.get("siteId") or [None])[0]
    if not (
        isinstance(partner_id, str)
        and partner_id.isdigit()
        and isinstance(site_id, str)
        and site_id.isdigit()
    ):
        return None
    return partner_id, site_id


def _questions(raw: object) -> dict[str, object]:
    if not isinstance(raw, list):
        return {}
    result: dict[str, object] = {}
    for question in raw:
        if not isinstance(question, dict):
            continue
        name = question.get("QuestionName")
        if isinstance(name, str) and name:
            result[name.casefold()] = question.get("Value")
    return result


def _safe_date(value: object) -> str | None:
    raw = _clean_string(value)
    if raw is None:
        return None
    try:
        return datetime.strptime(raw, "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def _location(questions: dict[str, object]) -> list[str] | None:
    parts: list[str] = []
    seen: set[str] = set()
    for key in ("formtext8", "formtext9", "formtext10"):
        part = _clean_string(questions.get(key))
        if part and part.casefold() not in seen:
            seen.add(part.casefold())
            parts.append(part)
    if parts:
        return [", ".join(parts)]
    location = _clean_string(questions.get("location"))
    return [location] if location else None


def _detail_location(body: str, expected_job_id: str) -> list[str]:
    parser = _PreloadParser()
    parser.feed(body)
    if not parser.value:
        raise ValueError(f"BrassRing detail {expected_job_id} omitted preLoadJSON")
    try:
        payload = json.loads(parser.value)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"BrassRing detail {expected_job_id} returned invalid preLoadJSON"
        ) from exc
    if not isinstance(payload, dict) or str(payload.get("JobId")) != expected_job_id:
        raise ValueError(f"BrassRing detail identity mismatch for {expected_job_id}")

    details = payload.get("Jobdetails")
    raw_questions = details.get("JobDetailQuestions") if isinstance(details, dict) else None
    if not isinstance(raw_questions, list):
        raise ValueError(f"BrassRing detail {expected_job_id} omitted its questions")
    questions: dict[str, object] = {}
    for question in raw_questions:
        if not isinstance(question, dict):
            continue
        zone = question.get("VerityZone")
        if isinstance(zone, str) and zone:
            questions[zone.casefold()] = question.get("AnswerValue")
    location = _location(questions)
    if location is None:
        raise ValueError(f"BrassRing detail {expected_job_id} omitted its location")
    return location


async def _hydrate_missing_locations(jobs: list[Job], client: httpx.AsyncClient) -> None:
    missing = [job for job in jobs if not job.locations]
    if not missing:
        return
    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def hydrate(job: Job) -> None:
        job_id = job.metadata.get("requisition_id") if isinstance(job.metadata, dict) else None
        if not isinstance(job_id, str):
            raise ValueError("BrassRing job omitted its requisition identity")
        async with semaphore:
            response = await client.get(job.url, follow_redirects=True, timeout=60)
        response.raise_for_status()
        job.locations = _detail_location(response.text, job_id)

    await asyncio.gather(*(hydrate(job) for job in missing))


def _parse_job(raw: object, partner_id: str, site_id: str) -> Job | None:
    if not isinstance(raw, dict):
        return None
    questions = _questions(raw.get("Questions"))
    job_id = _clean_string(questions.get("reqid"))
    title = _clean_string(questions.get("jobtitle"))
    link = _clean_string(raw.get("Link"))
    if not job_id or not job_id.isdigit() or not title or not link:
        return None

    link_ids = _board_ids(link)
    link_query = parse_qs(urlparse(link).query)
    link_job_id = (link_query.get("jobid") or [None])[0]
    if link_ids != (partner_id, site_id) or link_job_id != job_id:
        return None

    raw_description = questions.get("jobdescription") or questions.get("formtext3")
    description = raw_description if isinstance(raw_description, str) else None
    metadata: dict[str, object] = {
        "provider": "brassring",
        "requisition_id": job_id,
    }
    department = _clean_string(questions.get("department"))
    if department:
        metadata["department"] = department

    return Job(
        url=link,
        title=title,
        description=description,
        locations=_location(questions),
        date_posted=_safe_date(questions.get("lastupdated")),
        metadata=metadata,
    )


def _parse_page(payload: object) -> tuple[int, list[object], list[dict]]:
    if not isinstance(payload, dict):
        raise ValueError("BrassRing search returned a non-object response")
    total = payload.get("JobsCount")
    jobs_obj = payload.get("Jobs")
    rows = jobs_obj.get("Job") if isinstance(jobs_obj, dict) else None
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError("BrassRing search omitted a valid JobsCount")
    if rows is None and total == 0:
        rows = []
    if not isinstance(rows, list):
        raise ValueError("BrassRing search omitted its Jobs.Job list")
    sort_fields = payload.get("SortFields")
    sort_fields = sort_fields if isinstance(sort_fields, list) else []
    return total, rows, sort_fields


def _search_body(
    partner_id: str,
    site_id: str,
    cookie_value: str,
    *,
    page_number: int | None = None,
    sort_type: str | None = None,
) -> dict[str, object]:
    if page_number is None:
        return {
            "PartnerId": partner_id,
            "SiteId": site_id,
            "Keyword": "",
            "Location": "",
            "KeywordCustomSolrFields": [],
            "LocationCustomSolrFields": [],
            "FacetFilterFields": None,
            "TurnOffHttps": False,
            "Latitude": 0,
            "Longitude": 0,
            "PowerSearchOptions": {"PowerSearchOption": []},
            "encryptedsessionvalue": cookie_value,
        }
    return {
        "partnerId": partner_id,
        "siteId": site_id,
        "keyword": "",
        "location": "",
        "keywordCustomSolrFields": [],
        "locationCustomSolrFields": [],
        "linkId": "",
        "Latitude": 0,
        "Longitude": 0,
        "facetfilterfields": {"Facet": []},
        "powersearchoptions": {"PowerSearchOption": []},
        "SortType": sort_type or "",
        "pageNumber": page_number,
        "encryptedSessionValue": cookie_value,
    }


async def _snapshot(
    client: httpx.AsyncClient,
    board_url: str,
    partner_id: str,
    site_id: str,
) -> tuple[int, list[object], list[dict], str, str]:
    response = await client.get(board_url, follow_redirects=True)
    response.raise_for_status()
    body = response.text
    token = _TOKEN_RE.search(body)
    cookie = _COOKIE_VALUE_RE.search(body)
    if token is None or cookie is None:
        raise ValueError("BrassRing home page omitted its API session token")

    origin = f"{urlparse(board_url).scheme}://{urlparse(board_url).hostname}"
    headers = {
        **_HEADERS,
        "RFT": token.group(1),
        "origin": origin,
        "referer": board_url,
    }
    api_url = f"{origin}/TgNewUI/Search/Ajax/MatchedJobs"
    response = await client.post(
        api_url,
        headers=headers,
        json=_search_body(partner_id, site_id, cookie.group(1)),
        follow_redirects=True,
    )
    response.raise_for_status()
    total, rows, sort_fields = _parse_page(response.json())
    return total, rows, sort_fields, origin, cookie.group(1)


async def _fetch_page(
    client: httpx.AsyncClient,
    origin: str,
    partner_id: str,
    site_id: str,
    cookie_value: str,
    *,
    page_number: int,
    sort_type: str,
    referer: str,
) -> tuple[int, list[object]]:
    headers = {
        **_HEADERS,
        "origin": origin,
        "referer": referer,
    }
    response = await client.post(
        f"{origin}/TgNewUI/Search/Ajax/ProcessSortAndShowMoreJobs",
        headers=headers,
        json=_search_body(
            partner_id,
            site_id,
            cookie_value,
            page_number=page_number,
            sort_type=sort_type,
        ),
        follow_redirects=True,
    )
    response.raise_for_status()
    total, rows, _sort_fields = _parse_page(response.json())
    return total, rows


def _sort_type(sort_fields: list[dict]) -> str:
    for field in sort_fields:
        if isinstance(field, dict) and str(field.get("Value", "")).casefold() == "alphabetical":
            name = field.get("Name")
            if isinstance(name, str) and name:
                return name
    raise ValueError("BrassRing search omitted its alphabetical sort field")


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    ids = _board_ids(board.board_url)
    if ids is None:
        raise ValueError(f"Cannot derive BrassRing partner/site IDs from {board.board_url!r}")
    partner_id, site_id = ids
    total, first_rows, sort_fields, origin, cookie_value = await _snapshot(
        client, board.board_url, partner_id, site_id
    )
    if total > _MAX_JOBS:
        raise ValueError("BrassRing inventory exceeded the safety cap")

    raw_jobs: list[object] = []
    if total:
        row_size = len(first_rows) or _PAGE_SIZE
        expected_pages = math.ceil(total / row_size)
        if expected_pages == 1:
            raw_jobs = first_rows
        else:
            sort_type = _sort_type(sort_fields)
            for page_number in range(1, expected_pages + 1):
                page_total, rows = await _fetch_page(
                    client,
                    origin,
                    partner_id,
                    site_id,
                    cookie_value,
                    page_number=page_number,
                    sort_type=sort_type,
                    referer=board.board_url,
                )
                if page_total != total:
                    raise ValueError("BrassRing total changed during pagination")
                raw_jobs.extend(rows)

    if len(raw_jobs) != total:
        raise ValueError(f"BrassRing returned {len(raw_jobs)} rows for {total} jobs")

    jobs: list[Job] = []
    seen: set[str] = set()
    for raw in raw_jobs:
        job = _parse_job(raw, partner_id, site_id)
        if job is None:
            raise ValueError("BrassRing returned a row without valid job identity")
        job_id = job.metadata.get("requisition_id") if job.metadata else None
        if not isinstance(job_id, str) or job_id in seen:
            raise ValueError("BrassRing returned a duplicate or invalid requisition")
        seen.add(job_id)
        jobs.append(job)

    await _hydrate_missing_locations(jobs, client)
    return jobs
