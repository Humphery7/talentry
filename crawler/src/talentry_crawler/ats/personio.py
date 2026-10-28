"""Personio — GET https://{slug}.jobs.personio.{de,com}/xml?language={lang}"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_DOMAIN_RE = re.compile(r"^([\w-]+)\.jobs\.personio\.(\w+)$")
_IGNORE_SLUGS = frozenset({"www", "api", "app", "docs", "help", "support", "status"})
_KNOWN_DOMAINS = ("de", "com")
_SPECIFIC_EMPLOYMENT_TYPES = frozenset({"intern", "trainee", "freelance"})


def slug_from_url(board_url: str) -> str | None:
    host = (urlparse(board_url).hostname or "").lower()
    match = _DOMAIN_RE.match(host)
    if match and match.group(1) not in _IGNORE_SLUGS:
        return match.group(1)
    return None


def domain_from_url(board_url: str) -> str:
    host = (urlparse(board_url).hostname or "").lower()
    match = _DOMAIN_RE.match(host)
    return match.group(2) if match else "de"


def _api_url(slug: str, domain: str, language: str) -> str:
    return f"https://{slug}.jobs.personio.{domain}/xml?language={language}"


def _board_url(slug: str, domain: str) -> str:
    return f"https://{slug}.jobs.personio.{domain}"


def _text(element: ET.Element, tag: str) -> str | None:
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip() or None
    return None


def _parse_employment_type(position: ET.Element) -> str | None:
    employment_type = (_text(position, "employmentType") or "").lower()
    schedule = (_text(position, "schedule") or "").lower()
    if employment_type in _SPECIFIC_EMPLOYMENT_TYPES:
        return employment_type
    return schedule or None


def _parse_description(position: ET.Element) -> str | None:
    descriptions = position.find("jobDescriptions")
    if descriptions is None:
        return None

    parts: list[str] = []
    for description in descriptions.findall("jobDescription"):
        name = _text(description, "name")
        value = _text(description, "value")
        if value:
            parts.append(f"<h3>{name}</h3>\n{value}" if name else value)
    return "\n".join(parts) or None


def _parse_job(position: ET.Element, slug: str, domain: str) -> Job | None:
    job_id = _text(position, "id")
    if not job_id:
        return None

    metadata: dict = {"id": job_id}
    for field in (
        "department",
        "subcompany",
        "recruitingCategory",
        "seniority",
        "yearsOfExperience",
        "occupation",
        "occupationCategory",
        "keywords",
    ):
        value = _text(position, field)
        if value:
            metadata[field] = value

    office = _text(position, "office")
    return Job(
        url=f"{_board_url(slug, domain)}/job/{job_id}",
        title=_text(position, "name"),
        description=_parse_description(position),
        locations=[office] if office else None,
        employment_type=_parse_employment_type(position),
        date_posted=_text(position, "createdAt"),
        metadata=metadata,
    )


async def _fetch_xml_jobs(
    slug: str, domain: str, language: str, client: httpx.AsyncClient
) -> list[Job] | None:
    response = await client.get(_api_url(slug, domain, language), follow_redirects=True)
    if response.status_code != 200:
        return None

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError:
        return None

    jobs: list[Job] = []
    for position in root.findall(".//position"):
        parsed = _parse_job(position, slug, domain)
        if parsed is not None:
            jobs.append(parsed)
    return jobs


def _parse_html_jobs(html: str, slug: str, domain: str) -> list[Job]:
    escaped_slug = re.escape(slug)
    patterns = (
        re.compile(
            r'\\"jobs\\":\s*(\[\{.*?\}])\s*,\s*\\"subdomain\\":\s*\\"'
            + escaped_slug
            + r'\\"',
            re.DOTALL,
        ),
        re.compile(
            r'"jobs":\s*(\[\{.*?\}])\s*,\s*"subdomain"\s*:\s*"' + escaped_slug + r'"',
            re.DOTALL,
        ),
    )

    raw_json = None
    for pattern in patterns:
        match = pattern.search(html)
        if match:
            raw_json = match.group(1).replace('\\"', '"')
            break
    if raw_json is None:
        return []

    try:
        items = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []

    jobs: list[Job] = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        employment_type = (item.get("employment_type") or "").lower()
        schedule = (item.get("schedule") or "").lower()
        if employment_type not in _SPECIFIC_EMPLOYMENT_TYPES:
            employment_type = schedule or None
        office = item.get("main_office")
        jobs.append(
            Job(
                url=f"{_board_url(slug, domain)}/job/{item['id']}",
                title=item.get("name") if isinstance(item.get("name"), str) else None,
                locations=[office] if isinstance(office, str) and office else None,
                employment_type=employment_type,
                date_posted=item.get("created_at"),
            )
        )
    return jobs


async def _fetch_html_jobs(
    slug: str, domain: str, client: httpx.AsyncClient
) -> list[Job] | None:
    response = await client.get(f"{_board_url(slug, domain)}/", follow_redirects=True)
    if response.status_code != 200:
        return None
    return _parse_html_jobs(response.text, slug, domain)


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not slug:
        raise ValueError(
            f"Cannot derive Personio slug from {board.board_url!r} "
            "and no slug in monitor_config"
        )

    language = board.monitor_config.get("language")
    if not isinstance(language, str) or not language:
        language = "en"

    preferred = domain_from_url(board.board_url)
    domains = [preferred] + [domain for domain in _KNOWN_DOMAINS if domain != preferred]

    for domain in domains:
        jobs = await _fetch_xml_jobs(slug, domain, language, client)
        if jobs is not None:
            return jobs

    for domain in domains:
        jobs = await _fetch_html_jobs(slug, domain, client)
        if jobs:
            return jobs

    raise ValueError(f"Personio feed unavailable for {slug!r} on .de and .com")
