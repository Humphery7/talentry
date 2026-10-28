"""Jarvi — public offers API keyed by a per-company SDK key."""

from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from talentry_crawler.models import Board, Job

_API_URL = "https://functions.prod.jarvi.tech/v1/public-api/rest/v2/offers"
_MAX_JOBS = 50_000
_TAG_RE = re.compile(r"<[^>]+>")
_LOCATION_TEXT_RE = re.compile(
    r"Localisation\s*:\s*(?P<location>.*?)"
    r"(?=</p>|<br\s*/?>|(?:\s+-\s+)?Contrat\s*:|Rémunération\s*:|$)",
    re.IGNORECASE | re.DOTALL,
)
_SDK_RE = re.compile(r"data-sdk\s*=\s*(['\"])jarvi\1", re.IGNORECASE)
_PUBLIC_KEY_RE = re.compile(
    r"data-public-api-key\s*=\s*(['\"])(?P<key>[^'\"]+)\1", re.IGNORECASE
)
_CURRENCY_RE = re.compile(
    r"data-currency\s*=\s*(['\"])(?P<currency>[A-Za-z]{3})\1", re.IGNORECASE
)


def _field_values(raw: dict, purpose: str) -> list[dict]:
    values = raw.get("fieldsValues")
    if not isinstance(values, list):
        return []
    return [
        value
        for value in values
        if isinstance(value, dict)
        and isinstance(value.get("field"), dict)
        and value["field"].get("purpose") == purpose
    ]


def _field_value(raw: dict, purpose: str) -> str | None:
    for field in _field_values(raw, purpose):
        value = field.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _field_choice(raw: dict, purpose: str) -> str | None:
    for field in _field_values(raw, purpose):
        choice = field.get("fieldValue")
        if not isinstance(choice, dict):
            continue
        for key in ("technicalValue", "name"):
            value = choice.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _strip_html(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(html.unescape(_TAG_RE.sub(" ", value)).split())
    return cleaned or None


def _locations(raw: dict) -> list[str] | None:
    locations: list[str] = []
    for field in _field_values(raw, "joboffer_location"):
        location = field.get("location")
        if not isinstance(location, dict):
            continue
        name = next(
            (
                location.get(key)
                for key in ("formattedAddress", "search", "locality")
                if isinstance(location.get(key), str) and location[key].strip()
            ),
            None,
        )
        if name and name.strip() not in locations:
            locations.append(name.strip())
    if locations:
        return locations

    for purpose in ("joboffer_profile_description", "joboffer_description"):
        content = html.unescape(_field_value(raw, purpose) or "").replace("&nbsp;", " ")
        match = _LOCATION_TEXT_RE.search(content)
        fallback = _strip_html(match.group("location")) if match else None
        if fallback:
            return [fallback.strip(" -")]
    return None


def _slug(title: str) -> str:
    normalized = unicodedata.normalize("NFD", title.casefold())
    ascii_title = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9-]", "", re.sub(r"\s+", "-", ascii_title)).strip("-")


def _job_url(board_url: str, raw: dict, title: str) -> str | None:
    short_id = raw.get("shortId") or raw.get("id")
    if not isinstance(short_id, str) or not short_id.strip():
        return None
    short_id = short_id.strip()
    slug = _slug(title)
    query_value = f"{short_id}/{slug}" if slug else short_id

    parsed = urlsplit(board_url)
    query = [(key, value) for key, value in parse_qsl(parsed.query) if key != "q"]
    query.append(("q", query_value))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def _number(value: str | None) -> int | float | None:
    if value is None:
        return None
    try:
        number = float(value.strip().replace(",", "."))
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _salary(raw: dict, currency: object) -> dict | None:
    is_public = (_field_value(raw, "joboffer_salary_is_public") or "").casefold()
    if is_public != "true":
        return None
    minimum = _number(_field_value(raw, "joboffer_salary_per_year_min"))
    maximum = _number(_field_value(raw, "joboffer_salary_per_year_max"))
    if minimum is None and maximum is None:
        return None
    return {
        "currency": currency if isinstance(currency, str) else "EUR",
        "min": minimum,
        "max": maximum,
        "unit": "year",
    }


def _parse_job(raw: dict, board_url: str, currency: object) -> Job | None:
    title = _strip_html(_field_value(raw, "joboffer_title")) or _strip_html(raw.get("name"))
    if title is None:
        return None
    url = _job_url(board_url, raw, title)
    if url is None:
        return None

    company_description = _field_value(raw, "joboffer_company_description")
    responsibilities = _field_value(raw, "joboffer_description")
    qualifications = _field_value(raw, "joboffer_profile_description")
    description = "\n".join(
        part for part in (company_description, responsibilities, qualifications) if part
    ) or None

    remote_days = _number(_field_value(raw, "joboffer_remote_days_per_week"))
    workplace_type = "hybrid" if remote_days is not None and remote_days > 0 else None
    employment_type = _field_choice(raw, "joboffer_contract_type")
    if employment_type is None:
        is_fulltime = (_field_value(raw, "joboffer_is_fulltime") or "").casefold()
        employment_type = "full_time" if is_fulltime == "true" else None

    metadata = {
        key: value
        for key, value in {
            "source_id": raw.get("id"),
            "short_id": raw.get("shortId"),
            "updated_at": raw.get("updatedAt"),
            "minimum_years_experience": _number(
                _field_value(raw, "joboffer_min_years_of_experience")
            ),
            "responsibilities": responsibilities,
            "qualifications": qualifications,
        }.items()
        if value not in (None, "")
    }

    return Job(
        url=url,
        title=title,
        description=description,
        locations=_locations(raw),
        employment_type=employment_type,
        workplace_type=workplace_type,
        date_posted=raw.get("publishedAt") if isinstance(raw.get("publishedAt"), str) else None,
        salary=_salary(raw, currency),
        metadata=metadata,
    )


async def _board_metadata(board: Board, client: httpx.AsyncClient) -> dict:
    metadata = dict(board.monitor_config)
    if isinstance(metadata.get("public_api_key"), str):
        return metadata

    response = await client.get(board.board_url, follow_redirects=True)
    if response.status_code in {404, 410}:
        raise LookupError(f"Jarvi board {board.board_url!r} returned {response.status_code}")
    response.raise_for_status()
    page = response.text
    if _SDK_RE.search(page) is None:
        raise ValueError(f"Jarvi SDK configuration not found at {board.board_url!r}")
    key_match = _PUBLIC_KEY_RE.search(page)
    if key_match is None:
        raise ValueError(f"Jarvi public API key not found at {board.board_url!r}")
    metadata["public_api_key"] = html.unescape(key_match.group("key")).strip()
    currency_match = _CURRENCY_RE.search(page)
    if currency_match is not None:
        metadata["currency"] = currency_match.group("currency").upper()
    return metadata


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    metadata = await _board_metadata(board, client)
    key = metadata.get("public_api_key")
    if not isinstance(key, str) or not key:
        raise ValueError("Jarvi monitor_config omitted public_api_key")

    response = await client.get(
        _API_URL,
        params={"limit": _MAX_JOBS},
        headers={"x-api-key": key},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(f"Jarvi offers feed for {board.board_url!r} returned {response.status_code}")
    response.raise_for_status()

    payload = response.json()
    offers = payload.get("data") if isinstance(payload, dict) else None
    total = payload.get("total") if isinstance(payload, dict) else None
    if not isinstance(offers, list):
        raise ValueError("Jarvi offers payload omitted its data array")
    if total is not None and (isinstance(total, bool) or not isinstance(total, int)):
        raise ValueError("Jarvi offers payload returned an invalid total")
    if len(offers) > _MAX_JOBS:
        raise ValueError(f"Jarvi offers payload exceeds the {_MAX_JOBS:,}-job cap")

    return [
        job
        for raw in offers
        if isinstance(raw, dict)
        and (job := _parse_job(raw, board.board_url, metadata.get("currency")))
        is not None
    ]
