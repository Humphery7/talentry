"""Lever — GET https://api.lever.co/v0/postings/{token} (paginated)."""

from __future__ import annotations

import asyncio
import re

import httpx

from talentry_crawler.models import Board, Job

BATCH_SIZE = 100
_IGNORE_TOKENS = frozenset({"v0", "api", "js", "css", "assets"})
_EU_DOMAIN = re.compile(r"(?:api|jobs)\.eu\.lever\.co/")
_API_HEADERS = {"Accept": "application/json"}


def token_from_url(board_url: str) -> str | None:
    match = re.search(r"jobs\.(?:eu\.)?lever\.co/([\w-]+)", board_url)
    if match and match.group(1) not in _IGNORE_TOKENS:
        return match.group(1)
    return None


def region_from_url(url: str) -> str | None:
    return "eu" if _EU_DOMAIN.search(url) else None


def _api_url(token: str, region: str | None = None) -> str:
    if region == "eu":
        return f"https://api.eu.lever.co/v0/postings/{token}"
    return f"https://api.lever.co/v0/postings/{token}"


def _build_description(posting: dict) -> str | None:
    parts: list[str] = []
    description = posting.get("description")
    if description:
        parts.append(description)
    for item in posting.get("lists") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text", "")
        content = item.get("content", "")
        if text or content:
            parts.append(f"<h3>{text}</h3><ul>{content}</ul>")
    additional = posting.get("additional")
    if additional:
        parts.append(additional)
    return "\n".join(parts) if parts else None


def _parse_salary(salary_range: dict | None) -> dict | None:
    if not isinstance(salary_range, dict):
        return None
    sal_min = salary_range.get("min")
    sal_max = salary_range.get("max")
    if sal_min is None and sal_max is None:
        return None
    return {
        "currency": salary_range.get("currency"),
        "min": sal_min,
        "max": sal_max,
        "unit": salary_range.get("interval"),
    }


def _parse_job(posting: dict) -> Job | None:
    url = posting.get("hostedUrl")
    if not url:
        return None

    categories = posting.get("categories") or {}
    if not isinstance(categories, dict):
        categories = {}

    all_locations = categories.get("allLocations") or []
    if not all_locations:
        single = categories.get("location")
        all_locations = [single] if single else []

    metadata: dict = {}
    if categories.get("team"):
        metadata["team"] = categories["team"]
    if categories.get("department"):
        metadata["department"] = categories["department"]
    if posting.get("id"):
        metadata["id"] = posting["id"]

    return Job(
        url=url,
        title=posting.get("text") if isinstance(posting.get("text"), str) else None,
        description=_build_description(posting),
        locations=[loc for loc in all_locations if isinstance(loc, str)] or None,
        employment_type=categories.get("commitment")
        if isinstance(categories.get("commitment"), str)
        else None,
        workplace_type=posting.get("workplaceType")
        if isinstance(posting.get("workplaceType"), str)
        else None,
        salary=_parse_salary(posting.get("salaryRange")),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    token = board.monitor_config.get("token") or token_from_url(board.board_url)
    if not token:
        raise ValueError(
            f"Cannot derive Lever token from {board.board_url!r} "
            "and no token in monitor_config"
        )

    region = board.monitor_config.get("region") or region_from_url(board.board_url)
    base = _api_url(token, region)
    jobs: list[Job] = []
    skip = 0

    while True:
        response = await client.get(
            base,
            params={"limit": BATCH_SIZE, "skip": skip},
            headers=_API_HEADERS,
        )
        if response.status_code == 404 and skip == 0:
            raise LookupError(f"Lever board token {token!r} returned 404 (board gone)")
        response.raise_for_status()

        page = response.json()
        if not isinstance(page, list):
            raise ValueError("Lever response must be a JSON array")
        if not page:
            break

        for index, raw in enumerate(page):
            if not isinstance(raw, dict):
                raise ValueError(f"Lever posting at skip={skip}+{index} must be an object")
            parsed = _parse_job(raw)
            if parsed is not None:
                jobs.append(parsed)

        if len(page) < BATCH_SIZE:
            break
        skip += BATCH_SIZE
        await asyncio.sleep(0.5)

    return jobs
