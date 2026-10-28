"""eArcu — public live-vacancy XML feed."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse

import httpx

from talentry_crawler.models import Board, Job

_MAX_JOBS = 50_000


def _text(element: ET.Element, tag: str) -> str | None:
    child = element.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _candidate_feed_urls(board_url: str) -> list[str]:
    try:
        parsed = urlparse(board_url)
        port = parsed.port
    except ValueError:
        return []
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
    ):
        return []

    origin = f"https://{parsed.hostname.casefold()}"
    path = parsed.path.rstrip("/")
    prefixes: list[str] = []
    marker = "/vacancy/"
    if marker in path.casefold():
        marker_at = path.casefold().index(marker)
        prefixes.append(path[:marker_at])
    elif path:
        prefixes.append(f"/{path.strip('/').split('/', 1)[0]}")
    prefixes.append("")

    urls: list[str] = []
    for prefix in prefixes:
        candidate = f"{origin}{prefix}/allvacancies/"
        if candidate not in urls:
            urls.append(candidate)
    return urls


def _canonical_job_url(feed_url: str, raw_url: str) -> str | None:
    try:
        feed = urlparse(feed_url)
        candidate = urlparse(urljoin(feed_url, raw_url))
        feed_port = feed.port
        candidate_port = candidate.port
    except ValueError:
        return None

    feed_suffix = "/allvacancies/"
    if not feed.path.casefold().endswith(feed_suffix):
        return None
    portal_prefix = feed.path[: -len(feed_suffix)]
    vacancy_prefix = f"{portal_prefix}/vacancy/"
    if (
        feed.scheme.casefold() != "https"
        or candidate.scheme.casefold() != "https"
        or feed.hostname is None
        or candidate.hostname is None
        or candidate.hostname.casefold() != feed.hostname.casefold()
        or feed.username is not None
        or feed.password is not None
        or candidate.username is not None
        or candidate.password is not None
        or feed_port not in {None, 443}
        or candidate_port not in {None, 443}
        or feed.query
        or feed.fragment
        or candidate.query
        or candidate.fragment
        or not candidate.path.casefold().startswith(vacancy_prefix.casefold())
    ):
        return None
    return candidate._replace(scheme="https", netloc=feed.hostname.casefold()).geturl()


def _parse_feed(text: str, feed_url: str) -> list[Job]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid eArcu XML at {feed_url}") from exc
    if root.tag.casefold() != "positions":
        raise ValueError(f"Unexpected eArcu root element at {feed_url}: {root.tag}")

    jobs: list[Job] = []
    seen_urls: set[str] = set()
    for position in root.findall("position"):
        raw_url = _text(position, "DescriptionURL")
        title = _text(position, "JobTitle")
        if not raw_url or not title:
            raise ValueError(f"eArcu position missing URL or title at {feed_url}")
        url = _canonical_job_url(feed_url, raw_url)
        if url is None:
            raise ValueError(f"eArcu position has an unsafe job URL at {feed_url}")
        if url in seen_urls:
            raise ValueError(f"eArcu feed contains a duplicate job URL at {feed_url}")
        seen_urls.add(url)

        locations = [
            location.text.strip()
            for location in position.findall("./Locations/Location")
            if location.text and location.text.strip()
        ]
        metadata = {
            key: value
            for key, value in {
                "reference": _text(position, "VacancyRef"),
                "job_function": _text(position, "JobFunction"),
                "brand": _text(position, "Brand"),
                "salary_description": _text(position, "DisplaySalaryDescription"),
            }.items()
            if value is not None
        }
        jobs.append(
            Job(
                url=url,
                title=title,
                description=_text(position, "Description"),
                locations=locations or None,
                date_posted=_text(position, "LastPublishedDate"),
                metadata=metadata or None,
            )
        )

    if len(jobs) > _MAX_JOBS:
        raise ValueError(f"eArcu feed exceeds {_MAX_JOBS} jobs at {feed_url}")
    return jobs


def _validated_feed_url(board: Board, candidates: list[str]) -> str:
    configured = board.monitor_config.get("feed_url")
    if configured is None:
        if not candidates:
            raise ValueError(f"Unsafe eArcu board URL: {board.board_url!r}")
        return candidates[0]
    if not isinstance(configured, str) or configured not in candidates:
        raise ValueError(f"Unsafe eArcu feed URL for {board.board_url!r}")
    return configured


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    candidates = _candidate_feed_urls(board.board_url)
    if not candidates:
        raise ValueError(f"Unsafe eArcu board URL: {board.board_url!r}")
    feed_url = _validated_feed_url(board, candidates)
    response = await client.get(
        feed_url,
        headers={
            "accept": "application/xml,text/xml,*/*",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
            ),
        },
        follow_redirects=True,
    )
    response.raise_for_status()
    return _parse_feed(response.text, feed_url)
