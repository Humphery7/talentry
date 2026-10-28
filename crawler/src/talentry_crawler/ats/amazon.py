"""Amazon Jobs — public search JSON with capped pagination."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime

import httpx

from talentry_crawler.models import Board, Job

_API_URL = "https://www.amazon.jobs/en/search.json"
_PAGE_SIZE = 100
_API_CAP = 10_000
_MAX_JOBS = 50_000
_CONCURRENCY = 5
_HEADERS = {"Accept-Encoding": "identity"}

_COUNTRY_CODES = [
    "USA",
    "CAN",
    "CRI",
    "MEX",
    "COL",
    "BRA",
    "GBR",
    "DEU",
    "FRA",
    "IRL",
    "ESP",
    "ITA",
    "NLD",
    "LUX",
    "POL",
    "ROU",
    "CZE",
    "BEL",
    "FIN",
    "CHE",
    "SVK",
    "IND",
    "CHN",
    "JPN",
    "SGP",
    "AUS",
    "KOR",
    "ISR",
    "ARE",
    "SAU",
    "ZAF",
    "EGY",
    "MYS",
    "PHL",
    "TWN",
    "TUR",
    "VNM",
    "NZL",
    "HKG",
    "THA",
    "IDN",
    "JOR",
    "BGD",
    "PER",
    "CHL",
    "ARG",
]

_CATEGORY_SLUGS = [
    "administrative-support",
    "audio-video-photography-production",
    "business-intelligence-data-engineering",
    "business-merchant-development",
    "buying-planning-instock-management",
    "customer-service",
    "data-science",
    "database-administration",
    "design",
    "economics",
    "editorial-writing-content-management",
    "facilities-maintenance-real-estate",
    "fgbs",
    "fulfillment-center-warehouse-associate",
    "fulfillment-operations-management",
    "hardware-development",
    "human-resources",
    "investigation-loss-prevention",
    "leadership-development-training",
    "legal",
    "machine-learning-science",
    "marketing",
    "medical-health-safety",
    "operations-it-support-engineering",
    "project-program-product-management-non-tech",
    "project-program-product-management-technical",
    "public-policy",
    "public-relations-communications",
    "research-science",
    "sales-advertising-account-management",
    "software-development",
    "solutions-architecture",
    "supply-chain-transportation-management",
    "systems-quality-security-engineering",
]

_SALARY_DOLLAR_RE = re.compile(
    r"\$([\d,]+(?:\.\d+)?)\s*/\s*(\w+).*?\$([\d,]+(?:\.\d+)?)\s*/\s*(\w+)"
)
_SALARY_RANGE_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*[-–—]\s*([\d,]+(?:\.\d+)?)\s+(\w{3})\s+"
    r"(annually|hourly|monthly|per hour|per year|per month)",
    re.IGNORECASE,
)
_UNIT_MAP = {
    "year": "year",
    "yearly": "year",
    "annual": "year",
    "annually": "year",
    "per year": "year",
    "hour": "hour",
    "hourly": "hour",
    "per hour": "hour",
    "month": "month",
    "monthly": "month",
    "per month": "month",
}


def _number(value: str) -> int | float:
    parsed = float(value.replace(",", ""))
    return int(parsed) if parsed.is_integer() else parsed


def _parse_salary(text: object) -> dict | None:
    if not isinstance(text, str) or not text:
        return None

    match = _SALARY_DOLLAR_RE.search(text)
    if match:
        minimum = _number(match.group(1))
        maximum = _number(match.group(3))
        unit = _UNIT_MAP.get(match.group(2).lower(), match.group(2).lower())
        return {"currency": "USD", "min": minimum, "max": maximum, "unit": unit}

    match = _SALARY_RANGE_RE.search(text)
    if match:
        minimum = _number(match.group(1))
        maximum = _number(match.group(2))
        unit = _UNIT_MAP.get(match.group(4).lower(), match.group(4).lower())
        return {
            "currency": match.group(3).upper(),
            "min": minimum,
            "max": maximum,
            "unit": unit,
        }
    return None


def _parse_date(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.strptime(" ".join(value.split()), "%B %d, %Y")
    except ValueError:
        return None
    return parsed.date().isoformat()


def _parse_job(raw: object) -> Job | None:
    if not isinstance(raw, dict):
        return None
    job_path = raw.get("job_path")
    title = raw.get("title")
    if not isinstance(job_path, str) or not job_path.startswith("/"):
        return None
    if not isinstance(title, str) or not title.strip():
        return None

    parts: list[str] = []
    description = raw.get("description")
    if isinstance(description, str) and description.strip():
        parts.append(description.strip())
    for source, heading in (
        ("basic_qualifications", "Basic Qualifications"),
        ("preferred_qualifications", "Preferred Qualifications"),
    ):
        value = raw.get(source)
        if isinstance(value, str) and value.strip():
            parts.append(f"<h3>{heading}</h3>\n{value.strip()}")

    location = raw.get("normalized_location") or raw.get("location")
    metadata = {
        key: raw[key]
        for key in (
            "id_icims",
            "job_category",
            "job_family",
            "business_category",
            "company_name",
            "country_code",
        )
        if raw.get(key) not in (None, "")
    }

    return Job(
        url=f"https://www.amazon.jobs{job_path}",
        title=title.strip(),
        description="\n".join(parts) or None,
        locations=[location] if isinstance(location, str) and location else None,
        employment_type=(
            raw.get("job_schedule_type")
            if isinstance(raw.get("job_schedule_type"), str)
            else None
        ),
        date_posted=_parse_date(raw.get("posted_date")),
        salary=_parse_salary(raw.get("salary")),
        metadata=metadata or None,
    )


async def _fetch_page(
    client: httpx.AsyncClient,
    params: dict,
) -> tuple[list[dict], int]:
    response = await client.get(
        _API_URL,
        params=params,
        headers=_HEADERS,
        follow_redirects=True,
    )
    if response.status_code in {404, 410} and params.get("offset", 0) == 0:
        raise LookupError("Amazon Jobs API is gone")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Amazon Jobs response must be an object")
    if payload.get("error"):
        raise ValueError(f"Amazon Jobs API error: {payload['error']}")
    hits = payload.get("hits")
    rows = payload.get("jobs") or []
    if (
        isinstance(hits, bool)
        or not isinstance(hits, int)
        or hits < 0
        or not isinstance(rows, list)
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise ValueError("Amazon Jobs response omitted a valid hits or jobs field")
    return rows, hits


async def _paginate(
    client: httpx.AsyncClient,
    base_params: dict,
) -> tuple[list[Job], int]:
    params = {**base_params, "result_limit": _PAGE_SIZE, "sort": "recent"}
    first_rows, total = await _fetch_page(client, {**params, "offset": 0})
    target = min(total, _API_CAP)
    rows = list(first_rows[:target])

    offsets = list(range(_PAGE_SIZE, target, _PAGE_SIZE))
    semaphore = asyncio.Semaphore(_CONCURRENCY)
    for start in range(0, len(offsets), _CONCURRENCY):
        window = offsets[start : start + _CONCURRENCY]

        async def fetch(offset: int) -> list[dict]:
            async with semaphore:
                page_rows, page_total = await _fetch_page(
                    client, {**params, "offset": offset}
                )
            if page_total != total:
                raise ValueError("Amazon Jobs inventory changed during pagination")
            return page_rows

        pages = await asyncio.gather(*(fetch(offset) for offset in window))
        for page_rows in pages:
            rows.extend(page_rows[: max(0, target - len(rows))])

    jobs: list[Job] = []
    seen: set[str] = set()
    for raw in rows:
        job = _parse_job(raw)
        if job is None or job.url in seen:
            continue
        seen.add(job.url)
        jobs.append(job)
    return jobs, total


async def _partition(
    client: httpx.AsyncClient,
    base_params: dict,
    initial_jobs: list[Job],
    initial_total: int,
) -> list[Job]:
    if initial_total < _API_CAP or "category[]" in base_params:
        return initial_jobs[:_MAX_JOBS]

    jobs = list(initial_jobs)
    seen = {job.url for job in jobs}

    if "country" not in base_params:
        country_codes = sorted(
            {
                str(job.metadata["country_code"])
                for job in initial_jobs
                if job.metadata and job.metadata.get("country_code")
            }
        ) or _COUNTRY_CODES
        for country in country_codes:
            country_jobs, country_total = await _paginate(
                client, {**base_params, "country": country}
            )
            additions = await _partition(
                client,
                {**base_params, "country": country},
                country_jobs,
                country_total,
            )
            for job in additions:
                if job.url not in seen:
                    seen.add(job.url)
                    jobs.append(job)
            if len(jobs) >= _MAX_JOBS:
                return jobs[:_MAX_JOBS]
        return jobs[:_MAX_JOBS]

    for category in _CATEGORY_SLUGS:
        category_jobs, category_total = await _paginate(
            client, {**base_params, "category[]": category}
        )
        if category_total == 0:
            continue
        for job in category_jobs:
            if job.url not in seen:
                seen.add(job.url)
                jobs.append(job)
        if len(jobs) >= _MAX_JOBS:
            return jobs[:_MAX_JOBS]
    return jobs[:_MAX_JOBS]


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    metadata = board.monitor_config
    base_params: dict[str, object] = {}
    if isinstance(metadata.get("country"), str):
        base_params["country"] = metadata["country"]
    if isinstance(metadata.get("category"), str):
        base_params["category[]"] = metadata["category"]
    if isinstance(metadata.get("business_category"), str):
        base_params["business_category[]"] = metadata["business_category"]

    jobs, total = await _paginate(client, base_params)
    return await _partition(client, base_params, jobs, total)
