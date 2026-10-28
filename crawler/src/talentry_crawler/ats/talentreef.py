"""TalentReef — public career-page definition + posting search APIs."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_BOARD_HOST = "apply.jobappnetwork.com"
_API_ORIGIN = "https://prod-kong.internal.talentreef.com/apply"
_ALIAS_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}", re.IGNORECASE)
_LOCALE_RE = re.compile(r"[a-z]{2}(?:-[a-z]{2})?")
_PAGE_SIZE = 1_000
_MAX_JOBS = 50_000


def identity_from_url(board_url: str) -> tuple[str, str] | None:
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
    ):
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if not parts or len(parts) > 2 or not _ALIAS_RE.fullmatch(parts[0]):
        return None
    locale = parts[1].lower() if len(parts) == 2 else "en"
    if not _LOCALE_RE.fullmatch(locale):
        return None
    return parts[0].lower(), locale


def _career_page_url(alias: str) -> str:
    return f"{_API_ORIGIN}/careerPages/alias/{alias}"


def _search_url(locale: str) -> str:
    return f"{_API_ORIGIN}/proxy-es/search-{locale}/posting/_search"


def _search_locale(locale: str) -> str:
    return "en-us" if locale == "en" else locale


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _locations(source: dict) -> list[str] | None:
    address = source.get("address")
    if not isinstance(address, dict):
        return None
    parts = [
        part
        for key in ("street1", "city", "stateOrProvince", "postalCode", "country")
        if (part := _clean_text(address.get(key))) is not None
    ]
    return [", ".join(parts)] if parts else None


async def _career_page(
    alias: str, locale: str, client: httpx.AsyncClient
) -> dict:
    response = await client.get(
        _career_page_url(alias),
        headers={
            "Accept": "application/json",
            "Referer": f"https://{_BOARD_HOST}/{alias}",
        },
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(
            f"TalentReef board {alias!r} returned {response.status_code} (board gone)"
        )
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("TalentReef career-page response must be a list")
    published = [
        item for item in payload if isinstance(item, dict) and item.get("published") is True
    ]
    if not published:
        raise ValueError(f"TalentReef board {alias!r} has no published career page")

    selected = next(
        (
            item
            for item in published
            if str(item.get("locale", "")).lower() == locale
        ),
        None,
    )
    if selected is None:
        selected = next(
            (item for item in published if item.get("defaultLocale") is True),
            published[0],
        )

    client_id = str(selected.get("clientId", "")).strip()
    brands = [
        brand.strip()
        for brand in selected.get("brands") or []
        if isinstance(brand, str) and brand.strip()
    ]
    if not client_id.isdigit() or not brands:
        raise ValueError("TalentReef career page omitted its client or brand scope")

    return {
        "alias": alias,
        "client_id": client_id,
        "locale": str(selected.get("locale") or locale).lower(),
        "brands": brands,
    }


def _search_payload(metadata: dict, start: int) -> dict:
    return {
        "from": start,
        "size": _PAGE_SIZE,
        "_source": [
            "positionType",
            "category",
            "description",
            "address",
            "jobId",
            "clientId",
            "clientName",
            "brandId",
            "brand",
            "internalOrExternal",
            "url",
            "postingUuid",
            "isSalaried",
            "minCompensation",
            "maxCompensation",
            "pubCompensation",
            "createdDate",
        ],
        "query": {
            "bool": {
                "filter": [
                    {"terms": {"clientId.raw": [str(metadata["client_id"])]}},
                    {"terms": {"brand.raw": list(metadata["brands"])}},
                    {
                        "terms": {
                            "internalOrExternal": [{"internalOrExternal": "externalOnly"}]
                        }
                    },
                ]
            }
        },
        "sort": [{"positionType.raw": {"order": "asc"}}],
    }


async def _search_page(
    metadata: dict, start: int, client: httpx.AsyncClient
) -> tuple[list[dict], int]:
    response = await client.post(
        _search_url(_search_locale(str(metadata["locale"]))),
        json=_search_payload(metadata, start),
        headers={
            "Accept": "application/json",
            "Referer": f"https://{_BOARD_HOST}/",
        },
    )
    response.raise_for_status()
    payload = response.json()
    hits = payload.get("hits") if isinstance(payload, dict) else None
    raw_hits = hits.get("hits") if isinstance(hits, dict) else None
    if not isinstance(raw_hits, list):
        raise ValueError("TalentReef posting search omitted its hits list")

    total = hits.get("total", 0)
    if isinstance(total, dict):
        total = total.get("value", 0)
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError("TalentReef posting search returned an invalid total")

    return [hit for hit in raw_hits if isinstance(hit, dict)], total


def _parse_job(hit: dict, metadata: dict) -> Job | None:
    source = hit.get("_source")
    if not isinstance(source, dict):
        return None
    job_id = source.get("jobId")
    if job_id in (None, "") or isinstance(job_id, bool):
        return None
    title = _clean_text(source.get("positionType"))
    if title is None:
        return None

    client_id = str(metadata["client_id"])
    locale = str(metadata["locale"])
    job_metadata = {
        key: value
        for key, value in {
            "job_id": job_id,
            "posting_uuid": source.get("postingUuid"),
            "brand": source.get("brand"),
            "client_name": source.get("clientName"),
        }.items()
        if value not in (None, "")
    }

    return Job(
        url=f"https://{_BOARD_HOST}/clients/{client_id}/posting/{job_id}/{locale}",
        title=title,
        description=_clean_text(source.get("description")),
        locations=_locations(source),
        employment_type=_clean_text(source.get("category")),
        date_posted=_clean_text(source.get("createdDate")),
        metadata=job_metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    configured = board.monitor_config
    identity = identity_from_url(board.board_url)
    alias = configured.get("alias") or (identity[0] if identity else None)
    locale = configured.get("locale") or (identity[1] if identity else "en")
    if not isinstance(alias, str) or not _ALIAS_RE.fullmatch(alias):
        raise ValueError("Cannot derive a valid TalentReef career-page alias")

    metadata = await _career_page(alias.lower(), str(locale).lower(), client)
    hits: list[dict] = []
    total = 0

    while len(hits) < _MAX_JOBS:
        page, total = await _search_page(metadata, len(hits), client)
        hits.extend(page)
        if len(hits) >= total:
            break
        if not page:
            raise ValueError("TalentReef search stopped before its advertised total")

    jobs: list[Job] = []
    seen: set[str] = set()
    for hit in hits:
        job = _parse_job(hit, metadata)
        if job is not None and job.url not in seen:
            seen.add(job.url)
            jobs.append(job)

    if hits and not jobs:
        raise ValueError("TalentReef posting search returned no valid jobs")
    return jobs
