"""Welcome to the Jungle — public organization and Algolia jobs APIs."""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlencode, urlparse

import httpx

from talentry_crawler.models import Board, Job

_MAX_JOBS = 1_000
_DETAIL_CONCURRENCY = 10
_SITE = "https://www.welcometothejungle.com"
_API = "https://api.welcometothejungle.com/api/v1"
_ALGOLIA_URL = "https://csekhvms53-dsn.algolia.net/1/indexes/*/queries"
_ALGOLIA_INDEX = "wk_cms_jobs_production"
_ALGOLIA_HEADERS = {
    "x-algolia-application-id": "CSEKHVMS53",
    "x-algolia-api-key": "4bd8f6215d0cc52b26430765769e65a0",
    "content-type": "application/x-www-form-urlencoded",
    "origin": _SITE,
    "referer": f"{_SITE}/",
}
_HOSTS = frozenset({"welcometothejungle.com", "www.welcometothejungle.com"})
_COMPANY_PATH_RE = re.compile(r"^/([a-z]{2})/companies/([^/]+)(?:/|$)", re.IGNORECASE)
_SALARY_UNITS = {
    "year": "year",
    "yearly": "year",
    "annual": "year",
    "annually": "year",
    "month": "month",
    "monthly": "month",
    "day": "day",
    "daily": "day",
    "hour": "hour",
    "hourly": "hour",
}
_REMOTE_TYPES = {
    "remote": "remote",
    "full": "remote",
    "full_time": "remote",
    "full-time": "remote",
    "partial": "hybrid",
    "hybrid": "hybrid",
    "none": "onsite",
    "no": "onsite",
    "onsite": "onsite",
    "on-site": "onsite",
}


def _identity_from_url(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() not in _HOSTS:
        return None
    match = _COMPANY_PATH_RE.match(parsed.path)
    return (match.group(1).lower(), match.group(2)) if match else None


def _organization_url(slug: str) -> str:
    return f"{_API}/organizations/{slug}"


def _detail_url(slug: str, job_slug: str) -> str:
    return f"{_API}/organizations/{slug}/jobs/{job_slug}"


def _public_job_url(locale: str, slug: str, job_slug: str) -> str:
    return f"{_SITE}/{locale}/companies/{slug}/jobs/{job_slug}"


def _localized(value: object, language: str | None) -> str | None:
    if isinstance(value, str):
        return value or None
    if not isinstance(value, dict):
        return None
    for key in (language, "en", "fr", "es", "cs", "sk"):
        if key and isinstance(value.get(key), str) and value[key]:
            return value[key]
    return None


async def _fetch_organization(slug: str, client: httpx.AsyncClient) -> dict | None:
    response = await client.get(_organization_url(slug), follow_redirects=True)
    if response.status_code in {404, 410}:
        return None
    response.raise_for_status()
    payload = response.json()
    organization = payload.get("organization") if isinstance(payload, dict) else None
    return organization if isinstance(organization, dict) else None


async def _fetch_summaries(
    organization_slug: str,
    client: httpx.AsyncClient,
) -> tuple[list[dict], bool]:
    params = urlencode(
        {
            "hitsPerPage": _MAX_JOBS,
            "page": 0,
            "filters": f"organization.slug:{organization_slug}",
        }
    )
    body = {"requests": [{"indexName": _ALGOLIA_INDEX, "params": params}]}
    response = await client.post(
        _ALGOLIA_URL,
        headers=_ALGOLIA_HEADERS,
        content=json.dumps(body, separators=(",", ":")),
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise ValueError("WTTJ Algolia response is missing its results array")

    result = results[0]
    raw_hits = result.get("hits")
    if not isinstance(raw_hits, list):
        raise ValueError("WTTJ Algolia response is missing its hits array")
    hits = [hit for hit in raw_hits if isinstance(hit, dict)]
    total = result.get("nbHits")
    truncated = isinstance(total, int) and total > _MAX_JOBS
    return hits, truncated


def _deduplicate_summaries(hits: list[dict], public_slug: str) -> list[dict]:
    deduped: dict[str, dict] = {}
    for hit in hits:
        job_slug = hit.get("slug")
        if not isinstance(job_slug, str) or not job_slug:
            continue
        reference = hit.get("reference")
        key = reference if isinstance(reference, str) and reference else job_slug
        current = deduped.get(key)
        website = hit.get("website")
        is_company_copy = isinstance(website, dict) and website.get("reference") == public_slug
        if current is None:
            deduped[key] = hit
            continue
        current_website = current.get("website")
        current_is_company_copy = (
            isinstance(current_website, dict)
            and current_website.get("reference") == public_slug
        )
        if is_company_copy and not current_is_company_copy:
            deduped[key] = hit
    return list(deduped.values())


def _locations(raw: dict) -> list[str] | None:
    offices = raw.get("offices")
    if not isinstance(offices, list):
        office = raw.get("office")
        offices = [office] if isinstance(office, dict) else []

    locations: list[str] = []
    seen: set[str] = set()
    for office in offices:
        if not isinstance(office, dict):
            continue
        value = office.get("local_address") or office.get("address") or office.get("city")
        if isinstance(value, str) and value and value not in seen:
            seen.add(value)
            locations.append(value)
    return locations or None


def _salary(raw: dict) -> dict | None:
    minimum = raw.get("salary_min")
    maximum = raw.get("salary_max")
    if minimum is None and maximum is None:
        return None
    unit = _SALARY_UNITS.get(str(raw.get("salary_period")).lower(), "year")
    return {
        "currency": raw.get("salary_currency"),
        "min": minimum,
        "max": maximum,
        "unit": unit,
    }


def _workplace_type(value: object) -> str | None:
    if value is True:
        return "remote"
    if isinstance(value, str):
        return _REMOTE_TYPES.get(value.casefold())
    return None


def _parse_job(raw: dict, *, locale: str, public_slug: str) -> Job | None:
    if raw.get("status") in {"archived", "expired", "closed"}:
        return None
    job_slug = raw.get("slug")
    title = raw.get("name")
    if not isinstance(job_slug, str) or not job_slug or not isinstance(title, str) or not title:
        return None

    language = raw.get("language") if isinstance(raw.get("language"), str) else locale
    extras: dict[str, object] = {}
    profile = raw.get("profile")
    if isinstance(profile, str) and profile:
        extras["qualifications"] = profile
    missions = raw.get("key_missions")
    if isinstance(missions, list) and missions:
        extras["responsibilities"] = missions
    skills = raw.get("skills")
    if isinstance(skills, list):
        names = [
            name
            for skill in skills
            if isinstance(skill, dict)
            if (name := _localized(skill.get("name"), language))
        ]
        if names:
            extras["skills"] = names

    metadata: dict[str, object] = {}
    for source in ("reference", "start_date"):
        value = raw.get(source)
        if value not in (None, ""):
            metadata[source] = value
    profession = raw.get("profession")
    if isinstance(profession, dict):
        profession_name = _localized(profession.get("name"), language)
        if profession_name:
            metadata["profession"] = profession_name

    return Job(
        url=_public_job_url(locale, public_slug, job_slug),
        title=title,
        description=raw.get("description") or None,
        locations=_locations(raw),
        employment_type=raw.get("contract_type") or None,
        workplace_type=_workplace_type(raw.get("remote")),
        date_posted=raw.get("published_at") or None,
        salary=_salary(raw),
        metadata=metadata or None,
    )


async def _fetch_detail(
    public_slug: str,
    job_slug: str,
    client: httpx.AsyncClient,
) -> dict | None:
    response = await client.get(
        _detail_url(public_slug, job_slug),
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        return None
    response.raise_for_status()
    payload = response.json()
    job = payload.get("job") if isinstance(payload, dict) else None
    if not isinstance(job, dict):
        raise ValueError("WTTJ detail response is missing its job object")
    return job


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    identity = _identity_from_url(board.board_url)
    metadata = board.monitor_config
    public_slug = metadata.get("slug")
    locale = metadata.get("locale")
    if identity:
        locale = locale or identity[0]
        public_slug = public_slug or identity[1]
    if not isinstance(public_slug, str) or not public_slug:
        raise ValueError(f"Cannot derive WTTJ company slug from {board.board_url!r}")
    if not isinstance(locale, str) or not locale:
        locale = "en"

    organization_slug = metadata.get("organization_slug")
    if not isinstance(organization_slug, str) or not organization_slug:
        organization = await _fetch_organization(public_slug, client)
        if not organization or not isinstance(organization.get("slug"), str):
            raise LookupError(f"WTTJ organization {public_slug!r} was not found")
        organization_slug = organization["slug"]

    raw_hits, truncated = await _fetch_summaries(organization_slug, client)
    summaries = _deduplicate_summaries(raw_hits, public_slug)
    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def hydrate(summary: dict) -> dict | None:
        async with semaphore:
            return await _fetch_detail(public_slug, summary["slug"], client)

    details = await asyncio.gather(*(hydrate(summary) for summary in summaries))
    jobs = [
        job
        for raw in details
        if raw is not None
        if (job := _parse_job(raw, locale=locale, public_slug=public_slug)) is not None
    ]
    return jobs[:_MAX_JOBS] if truncated else jobs
