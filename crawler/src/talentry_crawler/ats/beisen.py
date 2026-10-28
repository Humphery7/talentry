"""Beisen (zhiye.com) — public job listing API with HTML descriptions."""

from __future__ import annotations

import asyncio
import html
import json
import math
import re
from datetime import date
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_PAGE_SIZE = 1_000
_MAX_JOBS = 50_000
_BOOTSTRAP_RE = re.compile(r"\bvar\s+BSGlobal\s*=\s*")
_TENANT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_DISPLAY_FIELDS = [
    "Category",
    "Kind",
    "LocId",
    "DetailAddress",
    "Org",
    "Degree",
    "YearsOfWorking",
    "Salary",
    "PostDate",
]
_CHANNELS = {"1": "social", "2": "campus", "3": "intern"}


def _tenant_from_url(board_url: str) -> str | None:
    parsed = urlparse(board_url)
    host = (parsed.hostname or "").casefold()
    suffix = ".zhiye.com"
    if not host.endswith(suffix):
        return None
    tenant = host.removesuffix(suffix)
    return tenant if _TENANT_RE.fullmatch(tenant) else None


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(html.unescape(value).split())
    return cleaned or None


def _date(value: object) -> str | None:
    raw = _clean(value)
    if raw is None or raw.startswith("0001-"):
        return None
    match = _DATE_RE.match(raw)
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(0)).isoformat()
    except ValueError:
        return None


def _text_html(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    paragraphs: list[str] = []
    for part in re.split(r"\n\s*\n+", html.unescape(value).replace("\r\n", "\n")):
        lines = [
            html.escape(line.strip(), quote=False)
            for line in part.split("\n")
            if line.strip()
        ]
        if lines:
            paragraphs.append(f"<p>{'<br>'.join(lines)}</p>")
    return "\n".join(paragraphs) or None


def _description(raw: dict) -> str | None:
    sections: list[str] = []
    for heading, field in (("工作职责", "Duty"), ("任职资格", "Require")):
        body = _text_html(raw.get(field))
        if body:
            sections.extend((f"<h3>{heading}</h3>", body))
    return "\n".join(sections) or None


def _job_url(tenant: str, raw: dict, public_id: str) -> str:
    category_id = str(raw.get("CategoryId") or "1")
    channel = _CHANNELS.get(category_id, "social")
    return f"https://{tenant}.zhiye.com/{channel}/detail?jobAdId={public_id}"


def _parse_job(raw: dict, tenant: str) -> Job | None:
    if raw.get("Status") not in {None, 1}:
        return None
    public_id = raw.get("Id")
    title = _clean(raw.get("JobAdName"))
    if not isinstance(public_id, str) or _UUID_RE.fullmatch(public_id) is None:
        return None
    if title is None:
        return None

    locations: list[str] = []
    raw_locations = raw.get("LocNames")
    if isinstance(raw_locations, list):
        for value in raw_locations:
            location = _clean(value)
            if location and location not in locations:
                locations.append(location)
    if not locations:
        address = _clean(raw.get("DetailAddress"))
        if address:
            locations.append(address)

    metadata: dict[str, object] = {"id": public_id}
    for source, target in (
        ("JobAdId", "job_ad_id"),
        ("Category", "category"),
        ("CategoryId", "category_id"),
        ("Org", "organization"),
        ("OrgId", "organization_id"),
        ("Degree", "degree"),
        ("YearsOfWorking", "years_of_working"),
        ("Salary", "salary"),
    ):
        value = raw.get(source)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            if value != "":
                metadata[target] = value

    return Job(
        url=_job_url(tenant, raw, public_id),
        title=title,
        description=_description(raw),
        locations=locations or None,
        employment_type=_clean(raw.get("Kind")),
        date_posted=_date(raw.get("PostDate")),
        metadata=metadata,
    )


def _bootstrap_portal_id(page: str) -> str | None:
    match = _BOOTSTRAP_RE.search(page)
    if match is None:
        return None
    try:
        raw, _end = json.JSONDecoder().raw_decode(page, match.end())
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    portal_id = raw.get("PortalId")
    return portal_id if isinstance(portal_id, str) and _UUID_RE.fullmatch(portal_id) else None


async def _portal_id(
    tenant: str,
    client: httpx.AsyncClient,
    configured: object,
) -> str:
    if isinstance(configured, str) and _UUID_RE.fullmatch(configured):
        return configured
    if configured is not None:
        raise ValueError("Beisen portal_id must be a UUID")
    response = await client.get(f"https://{tenant}.zhiye.com/", follow_redirects=True)
    response.raise_for_status()
    portal_id = _bootstrap_portal_id(response.text)
    if portal_id is None:
        raise ValueError(f"Beisen tenant {tenant!r} did not expose a portal ID")
    return portal_id


async def _fetch_page(
    tenant: str,
    portal_id: str,
    page_index: int,
    client: httpx.AsyncClient,
) -> dict:
    response = await client.post(
        f"https://{tenant}.zhiye.com/api/Jobad/GetJobAdPageList",
        json={
            "PageIndex": page_index,
            "PageSize": _PAGE_SIZE,
            "KeyWords": "",
            "SpecialType": 0,
            "PortalId": portal_id,
            "DisplayFields": _DISPLAY_FIELDS,
        },
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Beisen tenant {tenant!r} returned an invalid payload")
    rows = payload.get("Data")
    count = payload.get("Count")
    if payload.get("Code") != 200 or not isinstance(rows, list):
        raise ValueError(f"Beisen tenant {tenant!r} returned an invalid listing")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"Beisen tenant {tenant!r} omitted its job count")
    return payload


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    metadata = board.monitor_config
    url_tenant = _tenant_from_url(board.board_url)
    configured_tenant = metadata.get("tenant")
    if configured_tenant is not None and configured_tenant != url_tenant:
        raise ValueError("Beisen tenant does not match the board URL")
    tenant = configured_tenant or url_tenant
    if not isinstance(tenant, str) or _TENANT_RE.fullmatch(tenant) is None:
        raise ValueError(f"Cannot derive Beisen tenant from {board.board_url!r}")

    portal_id = await _portal_id(tenant, client, metadata.get("portal_id"))
    first = await _fetch_page(tenant, portal_id, 0, client)
    total = first["Count"]
    page_count = max(1, math.ceil(total / _PAGE_SIZE))

    pages = [first]
    if page_count > 1:
        pages.extend(
            await asyncio.gather(
                *(
                    _fetch_page(tenant, portal_id, page_index, client)
                    for page_index in range(1, page_count)
                )
            )
        )

    jobs: list[Job] = []
    seen: set[str] = set()
    for page in pages:
        if page["Count"] != total:
            raise ValueError("Beisen job count changed during pagination")
        for raw in page["Data"]:
            if not isinstance(raw, dict):
                continue
            job = _parse_job(raw, tenant)
            if job is None or job.url in seen:
                continue
            seen.add(job.url)
            jobs.append(job)
            if len(jobs) >= _MAX_JOBS:
                return jobs
    return jobs
