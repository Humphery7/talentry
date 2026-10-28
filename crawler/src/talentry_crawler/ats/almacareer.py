"""AlmaCareer (Capybara) — public GraphQL widget API."""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urlparse

import httpx

from talentry_crawler.models import Board, Job

_GRAPHQL_URL = "https://api.capybara.lmc.cz/api/graphql/widget"
_DETAIL_CONCURRENCY = 8
_MAX_JOBS = 50_000
_DEFAULT_DETAIL_PATH = "detail-pozice"
_COUNTRY_BY_SUFFIX = {".jobs.cz": "cz", ".topjobs.sk": "sk"}
_IGNORE_SLUGS = frozenset({"www", "api", "cdn", "assets", "static", "app", "help"})

_WIDGET_ANCHOR_RE = re.compile(r'"widgets"\s*:\s*\{\s*"main"\s*:\s*\{')
_WIDGET_ID_RE = re.compile(r'"id"\s*:\s*"([0-9a-fA-F-]{36})"')
_API_KEY_RE = re.compile(r'"apiKey"\s*:\s*"([a-fA-F0-9]{32,})"')
_DETAIL_PATH_RE = re.compile(r'"detailPath"\s*:\s*"([^"]+)"')
_INLINE_PUSH_RE = re.compile(r"window\s*\.\s*__LMC_CAREER_WIDGET__\s*\.\s*push\s*\(\s*")
_REACT_CHUNK_RE = re.compile(r'["\'](react\.[A-Za-z0-9._-]+\.react\.min\.js)["\']')
_MAX_CHUNKS = 16
_WIDGET_ID_VALUE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_API_KEY_VALUE_RE = re.compile(r"^[a-f0-9]{32,256}$", re.IGNORECASE)

_EMPLOYMENT_TYPES = {
    "201300001": "full_time",
    "201300002": "part_time",
    "201300003": "contract",
    "201300004": "contract",
    "201300005": "internship",
    "201300006": "contract",
    "201300007": "part_time",
}
_SALARY_UNITS = {
    "měsíc": "month",
    "mesiac": "month",
    "month": "month",
    "hodina": "hour",
    "hour": "hour",
    "rok": "year",
    "year": "year",
}

_LISTING_QUERY = """
query LISTING_QUERY(
  $widgetId: ID!
  $host: String
  $page: Int
  $filters: [JobAdFilter!]!
  $useExampleData: Boolean!
  $rps: Int
) {
  widget(id: $widgetId, host: $host, useExampleData: $useExampleData) {
    config { languageIso }
    jobAdList(page: $page, filters: $filters, rps: $rps) {
      paginator {
        currentPage
        lastPage
        totalNumberOfItems
        numberOfItemsPerPage
      }
      groupedJobAds {
        ...jobAdGroup
        groups {
          ...jobAdGroup
          groups {
            ...jobAdGroup
            groups { ...jobAdGroup }
          }
        }
      }
    }
  }
}

fragment jobAdGroup on JobAdGroup {
  jobAds {
    id
    title
    validFrom
    languageIso
    teaser
    locations { country region district city cityPart }
    salary { min max period currency }
    employer { companyName }
    parameters { employmentTypesObjects { id label } }
    fieldsObjects { id label }
    professionsObjects { id label }
  }
}
""".strip()

_DETAIL_QUERY = """
query JOB_DETAIL(
  $widgetId: ID!
  $host: String
  $useExampleData: Boolean!
  $jobId: ID!
) {
  widget(id: $widgetId, host: $host, useExampleData: $useExampleData) {
    jobAd(id: $jobId) {
      id
      languageIso
      content { htmlContent }
    }
  }
}
""".strip()


def _match_country(host: str) -> tuple[str, str] | None:
    normalized = host.casefold().removeprefix("www.")
    for suffix, country in _COUNTRY_BY_SUFFIX.items():
        if normalized.endswith(suffix):
            slug = normalized.removesuffix(suffix)
            if slug and slug not in _IGNORE_SLUGS:
                return country, slug
    return None


def _host_from_board(board: Board) -> str | None:
    metadata = board.monitor_config
    configured = metadata.get("host")
    if isinstance(configured, str) and configured:
        return configured.casefold().removeprefix("www.")
    slug = metadata.get("slug")
    country = metadata.get("country")
    if isinstance(slug, str) and isinstance(country, str):
        suffix = next(
            (suffix for suffix, code in _COUNTRY_BY_SUFFIX.items() if code == country),
            None,
        )
        if suffix:
            return f"{slug.casefold()}{suffix}"
    parsed = urlparse(board.board_url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    return host if _match_country(host) else None


def _widget_config(script: str) -> dict[str, str] | None:
    anchor = _WIDGET_ANCHOR_RE.search(script)
    if anchor is None:
        return None
    window = script[anchor.end() : anchor.end() + 65_536]
    widget_id = _WIDGET_ID_RE.search(window)
    api_key = _API_KEY_RE.search(window)
    if widget_id is None or api_key is None:
        return None
    detail_path = _DETAIL_PATH_RE.search(window)
    return {
        "id": widget_id.group(1),
        "apiKey": api_key.group(1),
        "detail_path": detail_path.group(1) if detail_path else _DEFAULT_DETAIL_PATH,
    }


def _inline_widget_config(page: str) -> dict[str, str] | None:
    decoder = json.JSONDecoder()
    for anchor in _INLINE_PUSH_RE.finditer(page):
        try:
            raw, _end = decoder.raw_decode(page, anchor.end())
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue
        widget_id = raw.get("widgetId")
        api_key = raw.get("apiKey")
        if not isinstance(widget_id, str) or _WIDGET_ID_VALUE_RE.fullmatch(widget_id) is None:
            continue
        if not isinstance(api_key, str) or _API_KEY_VALUE_RE.fullmatch(api_key) is None:
            continue
        detail_path = raw.get("detailPath")
        return {
            "id": widget_id,
            "apiKey": api_key,
            "detail_path": (
                detail_path
                if isinstance(detail_path, str) and detail_path
                else _DEFAULT_DETAIL_PATH
            ),
        }
    return None


async def _chunk_widget_config(
    host: str,
    client: httpx.AsyncClient,
) -> dict[str, str] | None:
    loader = await client.get(f"https://{host}/assets/js/react.min.js", follow_redirects=True)
    if loader.status_code != 200:
        return None
    names = list(dict.fromkeys(_REACT_CHUNK_RE.findall(loader.text)))
    for name in names[:_MAX_CHUNKS]:
        response = await client.get(
            f"https://{host}/assets/js/{name}",
            follow_redirects=True,
        )
        if response.status_code == 200:
            config = _widget_config(response.text)
            if config is not None:
                return config
    return None


async def _fetch_widget_config(
    host: str,
    client: httpx.AsyncClient,
) -> dict[str, str] | None:
    response = await client.get(
        f"https://{host}/assets/js/script.min.js",
        follow_redirects=True,
    )
    if response.status_code == 200:
        config = _widget_config(response.text)
        if config is not None:
            return config
    elif response.status_code != 404:
        response.raise_for_status()

    config = await _chunk_widget_config(host, client)
    if config is not None:
        return config

    page = await client.get(f"https://{host}/", follow_redirects=True)
    if page.status_code != 200:
        return None
    return _inline_widget_config(page.text)


def _validate_config_value(
    value: object,
    pattern: re.Pattern[str],
    name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"AlmaCareer {name} is invalid")
    return value


async def _post_graphql(
    client: httpx.AsyncClient,
    *,
    query: str,
    variables: dict,
    api_key: str,
    host: str,
) -> dict:
    response = await client.post(
        _GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "origin": f"https://{host}",
            "referer": f"https://{host}/",
            "accept": "*/*",
        },
        follow_redirects=True,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("AlmaCareer GraphQL response is invalid")
    data = payload.get("data")
    errors = payload.get("errors")
    if errors and not data:
        message = errors[0].get("message") if isinstance(errors, list) and errors else errors
        raise ValueError(f"AlmaCareer GraphQL error: {message}")
    return data if isinstance(data, dict) else {}


def _flatten_groups(group: object) -> list[dict]:
    if not isinstance(group, dict):
        return []
    jobs = [item for item in group.get("jobAds") or [] if isinstance(item, dict)]
    for child in group.get("groups") or []:
        jobs.extend(_flatten_groups(child))
    return jobs


def _location(raw: dict) -> str | None:
    parts: list[str] = []
    for key in ("cityPart", "city", "district", "region", "country"):
        value = raw.get(key)
        if isinstance(value, str) and value and value not in parts:
            parts.append(value)
    return ", ".join(parts) or None


def _locations(values: object) -> list[str] | None:
    if not isinstance(values, list):
        return None
    locations: list[str] = []
    for value in values:
        if isinstance(value, dict):
            label = _location(value)
            if label and label not in locations:
                locations.append(label)
    return locations or None


def _salary(raw: dict | None) -> dict | None:
    if not isinstance(raw, dict):
        return None
    currency = raw.get("currency")
    if not isinstance(currency, str) or not currency:
        return None
    minimum = raw.get("min")
    maximum = raw.get("max")
    if minimum is None and maximum is None:
        return None
    unit = _SALARY_UNITS.get(str(raw.get("period") or "").casefold(), "month")
    return {"currency": currency, "min": minimum, "max": maximum, "unit": unit}


def _employment_type(parameters: object) -> str | None:
    if not isinstance(parameters, dict):
        return None
    types = parameters.get("employmentTypesObjects")
    if not isinstance(types, list):
        return None
    for item in types:
        if not isinstance(item, dict):
            continue
        type_id = str(item.get("id") or "")
        if type_id in _EMPLOYMENT_TYPES:
            return _EMPLOYMENT_TYPES[type_id]
        label = item.get("label")
        if isinstance(label, str) and label:
            return label
    return None


def _labels(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [
        item["label"]
        for item in values
        if isinstance(item, dict)
        and isinstance(item.get("label"), str)
        and item["label"]
    ]


def _date(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value[:10]
    return candidate if len(candidate) == 10 and candidate[4] == "-" else None


def _parse_job(raw: dict, *, host: str, detail_path: str, country: str) -> Job | None:
    job_id = raw.get("id")
    title = raw.get("title")
    if not isinstance(job_id, str) or not job_id:
        return None
    if not isinstance(title, str) or not title.strip():
        return None

    metadata: dict[str, object] = {"id": job_id, "country": country}
    employer = raw.get("employer")
    company = employer.get("companyName") if isinstance(employer, dict) else None
    if isinstance(company, str) and company:
        metadata["company_name"] = company
    fields = _labels(raw.get("fieldsObjects"))
    if fields:
        metadata["fields"] = fields
    professions = _labels(raw.get("professionsObjects"))
    if professions:
        metadata["professions"] = professions

    return Job(
        url=f"https://{host}/{detail_path}?r=detail&id={job_id}",
        title=title.strip(),
        description=raw.get("teaser") if isinstance(raw.get("teaser"), str) else None,
        locations=_locations(raw.get("locations")),
        employment_type=_employment_type(raw.get("parameters")),
        date_posted=_date(raw.get("validFrom")),
        salary=_salary(raw.get("salary")),
        metadata=metadata,
    )


async def _fetch_listing(
    client: httpx.AsyncClient,
    *,
    widget_id: str,
    api_key: str,
    host: str,
    page: int,
) -> dict:
    data = await _post_graphql(
        client,
        query=_LISTING_QUERY,
        variables={
            "widgetId": widget_id,
            "host": host,
            "useExampleData": False,
            "page": page,
            "filters": [],
            "rps": 100,
        },
        api_key=api_key,
        host=host,
    )
    widget = data.get("widget")
    listing = widget.get("jobAdList") if isinstance(widget, dict) else None
    if not isinstance(listing, dict):
        raise ValueError(f"AlmaCareer host {host!r} returned no jobAdList")
    return listing


async def _fetch_detail(
    client: httpx.AsyncClient,
    *,
    widget_id: str,
    api_key: str,
    host: str,
    job_id: str,
) -> str | None:
    data = await _post_graphql(
        client,
        query=_DETAIL_QUERY,
        variables={
            "widgetId": widget_id,
            "host": host,
            "useExampleData": False,
            "jobId": job_id,
        },
        api_key=api_key,
        host=host,
    )
    widget = data.get("widget")
    job = widget.get("jobAd") if isinstance(widget, dict) else None
    content = job.get("content") if isinstance(job, dict) else None
    html = content.get("htmlContent") if isinstance(content, dict) else None
    return html if isinstance(html, str) and html.strip() else None


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    metadata = board.monitor_config
    host = _host_from_board(board)
    if host is None:
        raise ValueError(f"Cannot derive AlmaCareer host from {board.board_url!r}")
    country_match = _match_country(host)
    country = country_match[0] if country_match else metadata.get("country", "cz")

    widget_id = _validate_config_value(
        metadata.get("widget_id"),
        _WIDGET_ID_VALUE_RE,
        "widget_id",
    )
    api_key = _validate_config_value(
        metadata.get("api_key"),
        _API_KEY_VALUE_RE,
        "api_key",
    )
    detail_path = metadata.get("detail_path")
    if detail_path is not None and not isinstance(detail_path, str):
        raise ValueError("AlmaCareer detail_path must be a string")

    if widget_id is None or api_key is None:
        config = await _fetch_widget_config(host, client)
        if config is None:
            raise ValueError(f"AlmaCareer widget config was not found for {host!r}")
        widget_id = widget_id or config["id"]
        api_key = api_key or config["apiKey"]
        detail_path = detail_path or config["detail_path"]
    detail_path = detail_path or _DEFAULT_DETAIL_PATH

    raw_ads: list[dict] = []
    page = 1
    last_page = 1
    while page <= last_page and len(raw_ads) < _MAX_JOBS:
        listing = await _fetch_listing(
            client,
            widget_id=widget_id,
            api_key=api_key,
            host=host,
            page=page,
        )
        raw_ads.extend(_flatten_groups(listing.get("groupedJobAds")))
        paginator = listing.get("paginator")
        if isinstance(paginator, dict):
            try:
                last_page = max(1, int(paginator.get("lastPage") or 1))
            except (TypeError, ValueError):
                last_page = 1
        page += 1

    jobs: list[Job] = []
    seen: set[str] = set()
    for raw in raw_ads:
        job = _parse_job(raw, host=host, detail_path=detail_path, country=country)
        if job is None or job.url in seen:
            continue
        seen.add(job.url)
        jobs.append(job)
        if len(jobs) >= _MAX_JOBS:
            break

    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def hydrate(job: Job) -> None:
        job_id = (job.metadata or {}).get("id")
        if not isinstance(job_id, str):
            return
        async with semaphore:
            html = await _fetch_detail(
                client,
                widget_id=widget_id,
                api_key=api_key,
                host=host,
                job_id=job_id,
            )
        if html:
            job.description = html

    if jobs:
        await asyncio.gather(*(hydrate(job) for job in jobs), return_exceptions=True)

    return jobs
