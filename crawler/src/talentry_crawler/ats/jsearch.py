"""JSearch (OpenWebNinja) — GET https://api.openwebninja.com/jsearch/search-v2

An aggregator, not an ATS: one search returns up to 10 postings harvested from
Google for Jobs (LinkedIn, Indeed, Glassdoor, Jooble, ...). So:

  * one boards.csv row is one saved search (query + country + window);
  * `num_pages` stays at 1 — every extra page costs another API credit, and
    breadth (more searches) beats depth (page 20 of the same search);
  * the posting's own employer is carried on the Job, because there is no
    "board company" here;
  * `external_id` (JSearch's job_uid) lets the pipeline store a posting once
    even when five different searches return it under five publisher URLs.

The description arrives as plain text, so it is turned into simple HTML: the
job page renders descriptions as HTML and the embedder strips tags.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from talentry_crawler.models import Board, Job

DEFAULT_API_URL = "https://api.openwebninja.com/jsearch/search-v2"
MAX_PAGES = 20  # API limit

# JSearch has no currency field. Infer it from the posting's country; when the
# country is unknown the salary keeps its numbers and simply omits the currency.
CURRENCY_BY_COUNTRY = {
    "AE": "AED",
    "AU": "AUD",
    "BR": "BRL",
    "CA": "CAD",
    "CH": "CHF",
    "CN": "CNY",
    "DE": "EUR",
    "EG": "EGP",
    "ES": "EUR",
    "FR": "EUR",
    "GB": "GBP",
    "GH": "GHS",
    "ID": "IDR",
    "IE": "EUR",
    "IN": "INR",
    "IT": "EUR",
    "JP": "JPY",
    "KE": "KES",
    "MX": "MXN",
    "MY": "MYR",
    "NG": "NGN",
    "NL": "EUR",
    "NZ": "NZD",
    "PH": "PHP",
    "PK": "PKR",
    "PL": "PLN",
    "QA": "QAR",
    "SA": "SAR",
    "SE": "SEK",
    "SG": "SGD",
    "TR": "TRY",
    "US": "USD",
    "ZA": "ZAR",
}

_SALARY_UNITS = {
    "year": "year",
    "annual": "year",
    "annually": "year",
    "month": "month",
    "monthly": "month",
    "week": "week",
    "weekly": "week",
    "day": "day",
    "daily": "day",
    "hour": "hour",
    "hourly": "hour",
}


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _slug(value: str) -> str:
    """Stable company slug, e.g. 'Canonical' -> 'canonical'."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if slug:
        return slug[:80].strip("-")
    # Non-latin employer names still need a non-empty primary key.
    return "employer-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def _html_from_text(text: str | None) -> str | None:
    """JSearch sends plain text; the job page and the crawler expect HTML."""
    if not text:
        return None
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if lines:
            body = "<br>".join(html.escape(line) for line in lines)
            paragraphs.append(f"<p>{body}</p>")
    return "\n".join(paragraphs) or None


def _apply_url(raw: dict[str, Any]) -> str | None:
    """Prefer an employer's own form; fall back to the publisher link.

    `job_google_link` is deliberately not used: it points at a Google search
    result, not an application, and JSearch always sends `job_apply_link`.
    """
    for option in raw.get("apply_options") or []:
        if isinstance(option, dict) and option.get("is_direct"):
            link = _text(option.get("apply_link"))
            if link and link.startswith(("http://", "https://")):
                return link
    link = _text(raw.get("job_apply_link"))
    if link and link.startswith(("http://", "https://")):
        return link
    return None


def _locations(raw: dict[str, Any]) -> list[str] | None:
    location = _text(raw.get("job_location"))
    if location:
        return [location]
    parts = [raw.get("job_city"), raw.get("job_state"), raw.get("job_country")]
    composed = ", ".join(
        part.strip() for part in parts if isinstance(part, str) and part.strip()
    )
    if composed:
        return [composed]
    if raw.get("job_is_remote") is True:
        return ["Remote"]
    return None


def _date_posted(raw: dict[str, Any]) -> str | None:
    stamp = _text(raw.get("job_posted_at_datetime_utc"))
    if stamp:
        return stamp[:10]
    seconds = raw.get("job_posted_at_timestamp")
    if isinstance(seconds, (int, float)):
        return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
    return None


def _salary(raw: dict[str, Any]) -> dict[str, Any] | None:
    low = raw.get("job_min_salary")
    high = raw.get("job_max_salary")
    if low is None and high is None:
        return None

    salary: dict[str, Any] = {
        "min": low if low is not None else high,
        "max": high if high is not None else low,
    }
    country = _text(raw.get("job_country"))
    currency = CURRENCY_BY_COUNTRY.get(country.upper()) if country else None
    if currency:
        salary["currency"] = currency
    unit = _SALARY_UNITS.get((_text(raw.get("job_salary_period")) or "").lower())
    if unit:
        salary["unit"] = unit
    return salary


def _workplace_type(raw: dict[str, Any]) -> str:
    # JSearch only distinguishes remote from everything else; there is no
    # hybrid signal, so "OnSite" is the honest default.
    return "Remote" if raw.get("job_is_remote") is True else "OnSite"


def _external_id(raw: dict[str, Any]) -> str | None:
    return _text(raw.get("job_uid")) or _text(raw.get("job_id"))


def _parse_job(raw: dict[str, Any]) -> Job | None:
    url = _apply_url(raw)
    title = _text(raw.get("job_title"))
    if not url or not title:
        return None

    employer = _text(raw.get("employer_name"))
    description = raw.get("job_description")
    metadata: dict[str, Any] = {}
    for key, value in (
        ("job_id", _text(raw.get("job_id"))),
        ("publisher", _text(raw.get("job_publisher"))),
        ("google_link", _text(raw.get("job_google_link"))),
        ("employment_types", raw.get("job_employment_types") or None),
    ):
        if value:
            metadata[key] = value
    if raw.get("job_apply_is_direct") is not None:
        metadata["apply_is_direct"] = bool(raw["job_apply_is_direct"])

    return Job(
        url=url,
        title=title,
        description=_html_from_text(description if isinstance(description, str) else None),
        locations=_locations(raw),
        employment_type=_text(raw.get("job_employment_type")),
        workplace_type=_workplace_type(raw),
        date_posted=_date_posted(raw),
        salary=_salary(raw),
        metadata=metadata or None,
        company_slug=_slug(employer) if employer else None,
        company_name=employer,
        company_logo_url=_text(raw.get("employer_logo")),
        company_website=_text(raw.get("employer_website")),
        external_id=_external_id(raw),
    )


def _api_key() -> str:
    key = os.environ.get("JSEARCH_API_KEY", "").strip().strip("\"'")
    if not key:
        raise RuntimeError(
            "JSEARCH_API_KEY is not set (add it to crawler/.env or the environment)"
        )
    return key


def _pages(config: dict[str, Any]) -> int:
    try:
        pages = int(config.get("num_pages", 1))
    except (TypeError, ValueError):
        pages = 1
    return max(1, min(MAX_PAGES, pages))


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    config = board.monitor_config
    query = _text(config.get("query"))
    if not query:
        raise ValueError(f"{board.board_slug} has no monitor_config.query")

    params: dict[str, Any] = {
        "query": query,
        "num_pages": _pages(config),
        "country": _text(config.get("country")) or "us",
    }
    for key in ("language", "date_posted"):
        value = _text(config.get(key))
        if value:
            params[key] = value

    response = await client.get(
        os.environ.get("JSEARCH_API_URL", DEFAULT_API_URL).strip() or DEFAULT_API_URL,
        params=params,
        headers={"X-API-Key": _api_key()},
    )
    if response.status_code in (401, 403):
        raise RuntimeError(
            f"JSearch rejected the API key (HTTP {response.status_code})"
        )
    if response.status_code == 429:
        raise RuntimeError("JSearch quota exhausted (HTTP 429)")
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("JSearch response must be a JSON object")
    if payload.get("status") != "OK":
        raise ValueError(f"JSearch returned status {payload.get('status')!r}")

    data = payload.get("data")
    raw_jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(raw_jobs, list):
        raise ValueError("JSearch response has no data.jobs list")

    jobs: list[Job] = []
    seen: set[str] = set()
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        job = _parse_job(raw)
        if job is None:
            continue
        identity = job.external_id or job.url
        if identity in seen:
            continue
        seen.add(identity)
        jobs.append(job)
    return jobs
