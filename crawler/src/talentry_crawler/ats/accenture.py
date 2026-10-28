"""Accenture — public job search API (multipart form, no browser session)."""

from __future__ import annotations

import asyncio

import httpx

from talentry_crawler.models import Board, Job

_API_BASE = "https://www.accenture.com/api/accenture"
_FINDJOBS = "elastic/findjobs"
_PAGE_SIZE = 500
_PAGINATION_CAP = 50_000
_BOUNDARY = "----TalentryFormBoundary"
_CONTENT_TYPE = f"multipart/form-data; boundary={_BOUNDARY}"
_HEADERS = {
    "accept": "application/json",
    "accept-encoding": "identity",
    "content-type": _CONTENT_TYPE,
}
_WORKPLACE_TYPES = {
    "on-site": "onsite",
    "onsite": "onsite",
    "office": "onsite",
    "remote": "remote",
    "hybrid": "hybrid",
}


def _multipart_body(
    *,
    start: int,
    country: str,
    language: str,
    site: str,
) -> str:
    fields = {
        "startIndex": str(start),
        "maxResultSize": str(_PAGE_SIZE),
        "jobKeyword": "",
        "jobCountry": country,
        "jobLanguage": language,
        "countrySite": site,
        "sortBy": "2",
        "totalHits": "true",
    }
    delimiter = f"--{_BOUNDARY}"
    parts = [
        f'{delimiter}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}'
        for name, value in fields.items()
    ]
    return "\r\n".join(parts) + f"\r\n{delimiter}--"


def _total_hits(value: object) -> int:
    if isinstance(value, dict):
        total = value.get("total")
        value = total if total is not None else value.get("value")
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Accenture response has an invalid totalHits value")
    return value


async def _fetch_page(
    client: httpx.AsyncClient,
    *,
    start: int,
    country: str,
    language: str,
    site: str,
) -> tuple[list[dict], int]:
    response = await client.post(
        f"{_API_BASE}/{_FINDJOBS}",
        content=_multipart_body(
            start=start,
            country=country,
            language=language,
            site=site,
        ),
        headers=_HEADERS,
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Accenture search response is not an object")
    rows = payload.get("data") or []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Accenture search response has an invalid data array")
    return rows, _total_hits(payload.get("totalHits"))


def _board_config(board: Board) -> tuple[str, str, str]:
    metadata = board.monitor_config
    country = metadata.get("country")
    language = metadata.get("language")
    site = metadata.get("site")
    for name, value in (("country", country), ("language", language), ("site", site)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Accenture {name} must be a non-empty string")
    return country.strip(), language.strip(), site.strip()


def _workplace_type(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return _WORKPLACE_TYPES.get(value.strip().casefold())


def _locations(value: object) -> list[str] | None:
    if isinstance(value, str):
        return [value] if value else None
    if isinstance(value, list):
        locations = [item for item in value if isinstance(item, str) and item]
        if locations:
            return locations
    return None


def _parse_job(raw: dict, site: str) -> Job | None:
    guid = raw.get("guid")
    title = raw.get("title")
    if not isinstance(guid, str) or not guid or not isinstance(title, str) or not title.strip():
        return None

    url = f"https://www.accenture.com/{site}/careers/jobdetails?id={guid}"

    metadata: dict[str, object] = {"guid": guid}
    for source, target in (
        ("businessArea", "business_area"),
        ("careerLevel", "career_level"),
        ("requisitionId", "requisition_id"),
    ):
        value = raw.get(source)
        if isinstance(value, (str, int)) and not isinstance(value, bool) and value != "":
            metadata[target] = value

    date_posted = raw.get("postedDate") or raw.get("updateDate")
    return Job(
        url=url,
        title=title.strip(),
        description=raw.get("jobDescription") if isinstance(raw.get("jobDescription"), str) else None,
        locations=_locations(raw.get("location")),
        workplace_type=_workplace_type(raw.get("remoteType")),
        date_posted=date_posted if isinstance(date_posted, str) else None,
        metadata=metadata,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    country, language, site = _board_config(board)
    first_rows, total = await _fetch_page(
        client,
        start=0,
        country=country,
        language=language,
        site=site,
    )

    offsets = range(_PAGE_SIZE, min(total, _PAGINATION_CAP), _PAGE_SIZE)
    pages = await asyncio.gather(
        *(
            _fetch_page(
                client,
                start=offset,
                country=country,
                language=language,
                site=site,
            )
            for offset in offsets
        )
    )
    raw_jobs = list(first_rows)
    for rows, page_total in pages:
        if page_total != total:
            raise ValueError("Accenture total changed during pagination")
        raw_jobs.extend(rows)
        if len(raw_jobs) >= min(total, _PAGINATION_CAP):
            break

    jobs: list[Job] = []
    seen: set[str] = set()
    for raw in raw_jobs:
        job = _parse_job(raw, site)
        if job is None or job.url in seen:
            continue
        seen.add(job.url)
        jobs.append(job)
    return jobs
