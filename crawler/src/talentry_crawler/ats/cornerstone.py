"""Cornerstone — public career-site bootstrap + paginated job search API."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, quote, urlparse

import httpx

from talentry_crawler.models import Board, Job

_TENANT_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CORP_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")
_CULTURE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")
_CONTEXT_RE = re.compile(r"\bcsod\.context\s*=\s*")
_TRUSTED_DOMAINS = frozenset({"csod.com", "csodfed.com"})
_RESERVED_TENANTS = frozenset({"api", "app", "help", "login", "portal", "support", "www"})
_PAGE_SIZE = 100
_MAX_JOBS = 50_000


@dataclass(frozen=True, slots=True)
class _Board:
    tenant: str
    site_id: int
    corp: str
    domain: str

    @property
    def host(self) -> str:
        return f"{self.tenant}.{self.domain}"

    def listing_url(self) -> str:
        return (
            f"https://{self.host}/ux/ats/careersite/{self.site_id}/home"
            f"?c={quote(self.corp, safe='')}"
        )

    def job_url(self, requisition_id: int) -> str:
        return (
            f"https://{self.host}/ux/ats/careersite/{self.site_id}/home/"
            f"requisition/{requisition_id}?c={quote(self.corp, safe='')}"
        )


def _token(value: object, pattern: re.Pattern[str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if pattern.fullmatch(normalized) else None


def _site_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        if not value.isdigit():
            return None
        value = int(value)
    if not isinstance(value, int) or not 1 <= value <= 2_147_483_647:
        return None
    return value


def _domain(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().rstrip(".")
    return normalized if normalized in _TRUSTED_DOMAINS else None


def _board_from_board(board: Board) -> _Board:
    config = board.monitor_config
    parsed = urlparse(board.board_url)
    host = (parsed.hostname or "").lower().rstrip(".")
    domain = _domain(config.get("domain"))
    if domain is None:
        domain = next(
            (candidate for candidate in _TRUSTED_DOMAINS if host.endswith(f".{candidate}")),
            None,
        )

    tenant = _token(config.get("tenant"), _TENANT_RE)
    if tenant is None and domain and host.endswith(f".{domain}"):
        tenant = _token(host.removesuffix(f".{domain}"), _TENANT_RE)

    site_id = _site_id(config.get("site_id"))
    corp = _token(config.get("corp"), _CORP_RE)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if site_id is None:
        site_id = _site_id(query.get("site"))
    if site_id is None:
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 5 and [part.lower() for part in parts[:3]] == [
            "ux",
            "ats",
            "careersite",
        ]:
            site_id = _site_id(parts[3])
    if corp is None:
        corp = _token(query.get("c"), _CORP_RE)

    if tenant is None or tenant in _RESERVED_TENANTS:
        raise ValueError(f"Cannot derive Cornerstone tenant from {board.board_url!r}")
    if site_id is None:
        raise ValueError(f"Cannot derive Cornerstone site_id from {board.board_url!r}")
    if corp is None:
        raise ValueError(f"Cannot derive Cornerstone corp from {board.board_url!r}")
    if domain is None:
        raise ValueError(f"Cannot derive Cornerstone domain from {board.board_url!r}")

    return _Board(tenant=tenant, site_id=site_id, corp=corp, domain=domain)


def _api_base(value: object, domain: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Cornerstone bootstrap omitted its API origin")
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https"
        or not (host == f"api.{domain}" or host.endswith(f".api.{domain}"))
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Cornerstone bootstrap returned an untrusted API origin")
    return f"https://{host}/"


def _context(page: str, board: _Board) -> dict:
    marker = _CONTEXT_RE.search(page)
    if marker is None:
        raise ValueError("Cornerstone listing omitted csod.context")
    try:
        raw, _ = json.JSONDecoder().raw_decode(page, marker.end())
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Cornerstone listing returned invalid context JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("Cornerstone listing context is not an object")
    if _token(raw.get("corp"), _CORP_RE) != board.corp:
        raise ValueError("Cornerstone listing context does not match the configured corporation")

    token = raw.get("token")
    if (
        not isinstance(token, str)
        or not 64 <= len(token) <= 20_000
        or len(token.split(".")) != 3
    ):
        raise ValueError("Cornerstone listing returned a malformed session token")
    culture_id = raw.get("cultureID")
    if isinstance(culture_id, bool) or not isinstance(culture_id, int) or culture_id <= 0:
        raise ValueError("Cornerstone listing returned an invalid culture ID")
    culture_name = raw.get("cultureName")
    if not isinstance(culture_name, str) or not _CULTURE_RE.fullmatch(culture_name):
        raise ValueError("Cornerstone listing returned an invalid culture name")
    endpoints = raw.get("endpoints")
    cloud = endpoints.get("cloud") if isinstance(endpoints, dict) else None

    return {
        "api_base": _api_base(cloud, board.domain),
        "token": token,
        "culture_id": culture_id,
        "culture_name": culture_name,
    }


async def _bootstrap(board: _Board, client: httpx.AsyncClient) -> dict:
    response = await client.get(board.listing_url(), follow_redirects=False)
    if response.status_code in {404, 410}:
        raise LookupError(
            f"Cornerstone board {board.tenant!r} returned {response.status_code} (board gone)"
        )
    response.raise_for_status()
    return _context(response.text, board)


def _search_payload(board: _Board, context: dict, page: int) -> dict:
    return {
        "careerSiteId": board.site_id,
        "careerSitePageId": board.site_id,
        "pageNumber": page,
        "pageSize": _PAGE_SIZE,
        "cultureId": context["culture_id"],
        "searchText": "",
        "cultureName": context["culture_name"],
        "states": [],
        "countryCodes": [],
        "cities": [],
        "placeID": "",
        "radius": None,
        "postingsWithinDays": None,
        "customFieldCheckboxKeys": [],
        "customFieldDropdowns": [],
        "customFieldRadios": [],
    }


async def _search_page(
    board: _Board, context: dict, page: int, client: httpx.AsyncClient
) -> tuple[int, list[dict]]:
    response = await client.post(
        f"{context['api_base']}rec-job-search/external/jobs",
        json=_search_payload(board, context, page),
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {context['token']}",
            "CSOD-Accept-Language": context["culture_name"],
        },
        follow_redirects=False,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("status") != "Success":
        raise ValueError(f"Cornerstone {board.tenant!r} search did not report success")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"Cornerstone {board.tenant!r} search omitted its data object")
    total = data.get("totalCount")
    rows = data.get("requisitions")
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ValueError(f"Cornerstone {board.tenant!r} search omitted a valid count")
    if not isinstance(rows, list):
        raise ValueError(f"Cornerstone {board.tenant!r} search omitted its requisitions")
    return total, [row for row in rows if isinstance(row, dict)]


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _locations(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    locations: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            continue
        location = ", ".join(
            part
            for key in ("city", "state", "country")
            if (part := _clean_text(raw.get(key))) is not None
        )
        if location and location not in seen:
            seen.add(location)
            locations.append(location)
    return locations or None


def _date(value: object, culture_name: str) -> str | None:
    raw = _clean_text(value)
    if raw is None or raw == "-":
        return None
    formats = ["%Y-%m-%d"]
    formats.extend(
        ["%m/%d/%Y", "%m-%d-%Y"]
        if culture_name.casefold() == "en-us"
        else ["%d/%m/%Y", "%d-%m-%Y"]
    )
    for format_ in formats:
        try:
            return datetime.strptime(raw, format_).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_job(raw: dict, board: _Board, culture_name: str) -> Job | None:
    requisition_id = raw.get("requisitionId")
    if isinstance(requisition_id, bool) or not isinstance(requisition_id, (int, str)):
        return None
    requisition = str(requisition_id)
    if not requisition.isdigit() or not 1 <= len(requisition) <= 20 or int(requisition) <= 0:
        return None

    title = _clean_text(raw.get("displayJobTitle"))
    if title is None:
        return None

    return Job(
        url=board.job_url(int(requisition)),
        title=title,
        description=_clean_text(raw.get("externalDescription")),
        locations=_locations(raw.get("locations")),
        date_posted=_date(raw.get("postingEffectiveDate"), culture_name),
        metadata={"requisition_id": int(requisition)},
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    identity = _board_from_board(board)
    context = await _bootstrap(identity, client)

    jobs: list[Job] = []
    seen: set[str] = set()
    raw_seen = 0
    total: int | None = None
    page = 1

    while page <= _MAX_JOBS // _PAGE_SIZE:
        page_total, rows = await _search_page(identity, context, page, client)
        if total is None:
            total = page_total
        elif page_total != total:
            raise ValueError(
                f"Cornerstone {identity.tenant!r} count changed during pagination "
                f"({total} -> {page_total})"
            )

        if not rows and raw_seen < page_total:
            raise ValueError(
                f"Cornerstone {identity.tenant!r} returned an empty page before its total"
            )

        for raw in rows:
            raw_seen += 1
            job = _parse_job(raw, identity, context["culture_name"])
            if job is not None and job.url not in seen:
                seen.add(job.url)
                jobs.append(job)

        if raw_seen >= page_total:
            break
        page += 1

    return jobs
