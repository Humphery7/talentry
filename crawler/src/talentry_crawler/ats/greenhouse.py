"""Greenhouse — GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urlparse

import httpx

from talentry_crawler.models import Board, Job

_IGNORE_TOKENS = frozenset({"embed", "v1", "api", "js", "css", "assets"})
_STRAY_TOGGLE_RE = re.compile(
    r"<a(?![^>]*\shref=)[^>]*>\s*(?:read|learn|show|see|view)\s+more\s*</a>",
    re.IGNORECASE,
)


def _clean_description(content: str | None) -> str | None:
    if not content:
        return None
    # Greenhouse sends its HTML "escaped" ("&lt;p&gt;Hello" instead of "<p>Hello").
    # Turn it back into real HTML, otherwise the website would show raw tags.
    if "<" not in content:
        content = html.unescape(content)
    return _STRAY_TOGGLE_RE.sub("", content)


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def token_from_url(board_url: str) -> str | None:
    parsed = urlparse(board_url)
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    def _clean(token: str | None) -> str | None:
        if not token:
            return None
        token = token.strip()
        if not token or token in _IGNORE_TOKENS:
            return None
        return token

    if host == "boards-api.greenhouse.io":
        if len(parts) >= 3 and parts[0] == "v1" and parts[1] == "boards":
            return _clean(parts[2])
        return None

    if host == "boards.greenhouse.io":
        if parts and parts[0] == "embed":
            return _clean(query.get("for", [None])[0])
        if parts:
            return _clean(parts[0])
        return None

    if re.fullmatch(r"job-boards(?:\.[\w-]+)?\.greenhouse\.io", host):
        if parts:
            return _clean(parts[0])
        return _clean(query.get("url_token", [None])[0] or query.get("for", [None])[0])

    return None


def _api_url(token: str) -> str:
    return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def _parse_job(raw: dict) -> Job | None:
    url = raw.get("absolute_url")
    if not url:
        return None

    locations: list[str] = []
    seen: set[str] = set()
    loc = raw.get("location")
    if isinstance(loc, dict) and loc.get("name"):
        name = _clean_text(loc["name"])
        if name:
            locations.append(name)
            seen.add(name)
    for office in raw.get("offices") or []:
        name = _clean_text(office.get("name") if isinstance(office, dict) else None)
        if name and name not in seen:
            locations.append(name)
            seen.add(name)

    metadata: dict = {}
    departments = [
        d.get("name")
        for d in (raw.get("departments") or [])
        if isinstance(d, dict) and d.get("name")
    ]
    if departments:
        metadata["departments"] = departments
    if raw.get("requisition_id"):
        metadata["requisition_id"] = raw["requisition_id"]

    return Job(
        url=url,
        title=_clean_text(raw.get("title")),
        description=_clean_description(raw.get("content")),
        locations=locations or None,
        date_posted=raw.get("first_published"),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    token = board.monitor_config.get("token") or token_from_url(board.board_url)
    if not token:
        raise ValueError(
            f"Cannot derive Greenhouse token from {board.board_url!r} "
            "and no token in monitor_config"
        )

    response = await client.get(_api_url(token), params={"content": "true"})
    if response.status_code == 404:
        raise LookupError(f"Greenhouse board token {token!r} returned 404 (board gone)")
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Greenhouse response must be a JSON object")
    raw_jobs = data.get("jobs")
    if not isinstance(raw_jobs, list):
        raise ValueError("Greenhouse response must contain a jobs list")

    jobs: list[Job] = []
    for index, raw in enumerate(raw_jobs):
        if not isinstance(raw, dict):
            raise ValueError(f"Greenhouse job at index {index} must be an object")
        parsed = _parse_job(raw)
        if parsed is None:
            raise ValueError(f"Greenhouse job at index {index} has no absolute_url")
        jobs.append(parsed)
    return jobs
