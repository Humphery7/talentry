"""Comeet — hosted-board positions data or tokenized public positions API."""

from __future__ import annotations

import html
import json
import re
from urllib.parse import parse_qs, urlparse

import httpx

from talentry_crawler.models import Board, Job

_API_URL = "https://www.comeet.co/careers-api/2.0/company/{company_id}/positions"
_POSITIONS_MARKER = "COMPANY_POSITIONS_DATA = "
_HOSTED_HOSTS = frozenset({"comeet.com", "www.comeet.com"})
_API_HOSTS = frozenset({"comeet.co", "www.comeet.co"})
_API_PATH_RE = re.compile(
    r"^/careers-api/2\.0/company/(?P<company_id>[A-Za-z0-9.]+)/positions/?$"
)
_MAX_JOBS = 50_000
_WORKPLACE_TYPES = {
    "remote": "remote",
    "hybrid": "hybrid",
    "on-site": "onsite",
    "onsite": "onsite",
    "office": "onsite",
}


def _board_parts(board_url: str) -> tuple[str, str] | None:
    parsed = urlparse(board_url)
    if (parsed.hostname or "").lower() not in _HOSTED_HOSTS:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0] != "jobs":
        return None
    company, board_id = parts[1], parts[2]
    if not company or not board_id:
        return None
    return company, board_id


def _hosted_url(board_url: str, config: dict) -> str:
    company = config.get("company")
    board_id = config.get("board_id")
    if isinstance(company, str) and isinstance(board_id, str):
        return f"https://www.comeet.com/jobs/{company}/{board_id}"
    parts = _board_parts(board_url)
    if parts is None:
        raise ValueError(
            f"Cannot derive Comeet company/board from {board_url!r} "
            "and no company/board_id in monitor_config"
        )
    return f"https://www.comeet.com/jobs/{parts[0]}/{parts[1]}"


def _api_credentials(board_url: str, config: dict) -> tuple[str, str] | None:
    company_id = config.get("company_id")
    token = config.get("token")
    if isinstance(company_id, str) and isinstance(token, str):
        return company_id, token
    parsed = urlparse(board_url)
    if (parsed.hostname or "").lower() not in _API_HOSTS:
        return None
    match = _API_PATH_RE.match(parsed.path)
    token_value = (parse_qs(parsed.query).get("token") or [None])[0]
    if match is None or not isinstance(token_value, str):
        return None
    return match.group("company_id"), token_value


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _locations(raw: dict) -> list[str] | None:
    location = raw.get("location")
    if isinstance(location, str):
        name = _clean_text(location)
        return [name] if name else None
    if not isinstance(location, dict):
        return None
    name = _clean_text(location.get("name"))
    if name:
        return [name]
    parts = [
        part
        for key in ("city", "state", "country")
        if (part := _clean_text(location.get(key))) is not None
    ]
    return [", ".join(parts)] if parts else None


def _details(raw: dict) -> list[dict]:
    details = raw.get("details")
    if not isinstance(details, list):
        custom_fields = raw.get("custom_fields")
        details = custom_fields.get("details") if isinstance(custom_fields, dict) else None
    if not isinstance(details, list):
        return []
    valid = [item for item in details if isinstance(item, dict)]
    valid.sort(
        key=lambda item: item.get("order")
        if isinstance(item.get("order"), int)
        else 0
    )
    return valid


def _content(raw: dict) -> tuple[str | None, dict[str, str]]:
    sections: list[str] = []
    qualifications: list[str] = []
    responsibilities: list[str] = []
    for detail in _details(raw):
        value = detail.get("value")
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        label = _clean_text(detail.get("name")) or "Details"
        sections.append(f"<h3>{html.escape(label)}</h3>\n{value}")
        normalized = label.casefold().replace("’", "'")
        if any(
            marker in normalized
            for marker in (
                "requirement",
                "qualification",
                "skill set",
                "who you are",
                "what you bring",
            )
        ):
            qualifications.append(value)
        if any(
            marker in normalized
            for marker in ("responsibilit", "what you'll", "what you will")
        ):
            responsibilities.append(value)

    extras: dict[str, str] = {}
    if qualifications:
        extras["qualifications"] = "\n".join(qualifications)
    if responsibilities:
        extras["responsibilities"] = "\n".join(responsibilities)
    return "\n".join(sections) or None, extras


def _workplace_type(raw: dict) -> str | None:
    value = _clean_text(raw.get("workplace_type"))
    if value:
        mapped = _WORKPLACE_TYPES.get(value.casefold())
        if mapped:
            return mapped
    location = raw.get("location")
    if isinstance(location, dict) and location.get("is_remote") is True:
        return "remote"
    return None


def _parse_job(raw: dict) -> Job | None:
    url = next(
        (
            raw.get(field)
            for field in (
                "url_active_page",
                "url_comeet_hosted_page",
                "url_recruit_hosted_page",
                "url_detected_page",
            )
            if isinstance(raw.get(field), str) and raw[field].strip()
        ),
        None,
    )
    title = _clean_text(raw.get("name"))
    if not isinstance(url, str) or title is None:
        return None

    description, extras = _content(raw)
    metadata = {
        key: raw[key]
        for key in ("uid", "department", "experience_level", "company_name", "time_updated")
        if raw.get(key) not in (None, "")
    }
    metadata.update(extras)

    return Job(
        url=url,
        title=title,
        description=description,
        locations=_locations(raw),
        employment_type=_clean_text(raw.get("employment_type")),
        workplace_type=_workplace_type(raw),
        date_posted=_clean_text(raw.get("time_updated")),
        metadata=metadata or None,
    )


def _positions_from_response(payload: object) -> list[dict] | None:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("positions"), list):
        return [item for item in payload["positions"] if isinstance(item, dict)]
    return None


def _positions_from_page(page: str) -> list[dict] | None:
    marker_index = page.find(_POSITIONS_MARKER)
    if marker_index < 0:
        return None
    payload = page[marker_index + len(_POSITIONS_MARKER) :].lstrip()
    try:
        value, _ = json.JSONDecoder().raw_decode(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Comeet embedded positions data is malformed") from exc
    return _positions_from_response(value)


async def _fetch_api_positions(
    company_id: str, token: str, client: httpx.AsyncClient
) -> list[dict]:
    response = await client.get(
        _API_URL.format(company_id=company_id),
        params={"token": token, "details": "true"},
        headers={"Accept": "application/json"},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(f"Comeet company {company_id!r} returned {response.status_code}")
    response.raise_for_status()
    positions = _positions_from_response(response.json())
    if positions is None:
        raise ValueError("Comeet API response omitted its positions")
    return positions


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    credentials = _api_credentials(board.board_url, board.monitor_config)
    if credentials is not None:
        positions = await _fetch_api_positions(*credentials, client)
    else:
        source = _hosted_url(board.board_url, board.monitor_config)
        response = await client.get(
            source,
            headers={"Accept": "text/html"},
            follow_redirects=True,
        )
        if response.status_code in {404, 410}:
            raise LookupError(f"Comeet board {source!r} returned {response.status_code}")
        response.raise_for_status()
        positions = _positions_from_page(response.text)
        if positions is None:
            raise ValueError(f"Comeet positions payload not found at {source!r}")

    jobs = [
        job for raw in positions[:_MAX_JOBS] if (job := _parse_job(raw)) is not None
    ]
    return jobs
