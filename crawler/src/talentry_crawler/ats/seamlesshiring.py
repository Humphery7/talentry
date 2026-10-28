"""SeamlessHiring — GET https://{tenant}.seamlesshiring.com/v2/jobs/job-list."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_HOST_RE = re.compile(r"^([a-z0-9-]+)\.seamlesshiring\.com$", re.IGNORECASE)
_PAGE_SIZE = 100
_MAX_JOBS = 50_000
_MAX_PAGES = 10_000
_WORKPLACE_TYPES = {
    "remote": "remote",
    "hybrid": "hybrid",
    "onsite": "onsite",
    "on-site": "onsite",
    "office": "onsite",
}


def tenant_from_url(board_url: str) -> str | None:
    host = (urlparse(board_url).hostname or "").lower()
    match = _HOST_RE.match(host)
    return match.group(1).lower() if match else None


def _base_url(tenant: str) -> str:
    return f"https://{tenant}.seamlesshiring.com"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _locations(post: dict) -> list[str] | None:
    location = post.get("location") or post.get("city")
    if not location and isinstance(post.get("location_details"), dict):
        location = post["location_details"].get("name")
    if isinstance(location, dict):
        location = (
            location.get("name")
            or location.get("city")
            or location.get("address")
        )
    cleaned = _clean_text(location)
    return [cleaned] if cleaned else None


def _workplace_type(value: object) -> str | None:
    cleaned = _clean_text(value)
    return _WORKPLACE_TYPES.get(cleaned.casefold()) if cleaned else None


def _parse_job(post: dict, tenant: str) -> Job | None:
    job_id = post.get("id")
    title = _clean_text(post.get("title"))
    if job_id in (None, "") or title is None:
        return None

    parts = [
        _clean_text(post.get("summary")),
        _clean_text(post.get("details")),
    ]
    description = "\n".join(part for part in parts if part) or None

    metadata = {
        key: value
        for key, value in {
            "id": job_id,
            "valid_through": post.get("expiry_date"),
            "position": post.get("position"),
        }.items()
        if value not in (None, "")
    }

    return Job(
        url=f"{_base_url(tenant)}/job/view/{job_id}",
        title=title,
        description=description,
        locations=_locations(post),
        employment_type=_clean_text(post.get("job_type")),
        workplace_type=_workplace_type(post.get("work_style")),
        date_posted=_clean_text(post.get("post_date")) or _clean_text(post.get("created_at")),
        metadata=metadata or None,
    )


async def _fetch_page(tenant: str, page: int, client: httpx.AsyncClient) -> dict:
    response = await client.get(
        f"{_base_url(tenant)}/v2/jobs/job-list",
        params={"limit": _PAGE_SIZE, "page": page},
        headers={"Accept": "application/json"},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(
            f"SeamlessHiring tenant {tenant!r} returned {response.status_code} (board gone)"
        )
    response.raise_for_status()

    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, dict):
        raise ValueError(f"SeamlessHiring response omitted jobs for tenant {tenant!r}")
    total = jobs.get("total")
    if (
        not isinstance(jobs.get("data"), list)
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
    ):
        raise ValueError(f"SeamlessHiring response has an invalid jobs page for {tenant!r}")
    return jobs


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    tenant = board.monitor_config.get("tenant") or tenant_from_url(board.board_url)
    if not isinstance(tenant, str) or not _HOST_RE.fullmatch(f"{tenant}.seamlesshiring.com"):
        raise ValueError(
            f"Cannot derive SeamlessHiring tenant from {board.board_url!r} "
            "and no tenant in monitor_config"
        )

    jobs: list[Job] = []
    seen_ids: set[str] = set()
    advertised: int | None = None
    page = 1

    while len(jobs) < _MAX_JOBS and page <= _MAX_PAGES:
        page_data = await _fetch_page(tenant, page, client)
        page_total = page_data["total"]
        if advertised is None:
            advertised = page_total
        elif page_total != advertised:
            raise ValueError(
                f"SeamlessHiring job count changed during pagination for {tenant!r}"
            )

        before = len(jobs)
        for post in page_data["data"]:
            if not isinstance(post, dict):
                continue
            parsed = _parse_job(post, tenant)
            if parsed is None:
                continue
            key = str((parsed.metadata or {}).get("id"))
            if key in seen_ids:
                continue
            seen_ids.add(key)
            jobs.append(parsed)
            if len(jobs) >= _MAX_JOBS:
                break

        if page_total == 0 or not page_data.get("next_page_url"):
            break
        if len(jobs) == before:
            raise ValueError(
                f"SeamlessHiring pagination made no progress for tenant {tenant!r}"
            )
        page += 1

    return jobs
