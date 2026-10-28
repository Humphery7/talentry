"""Woowa Brothers and Woowa Youths — public Korean careers API."""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qs, urlparse

import httpx

from talentry_crawler.models import Board, Job

_PAGE_SIZE = 500
_DETAIL_CONCURRENCY = 20
_MAX_JOBS = 50_000

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_RECRUIT_NUMBER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:$|[ T])")
_LOCATION_RE = re.compile(
    r"(?:근무\s*지역|모집\s*지역|근무지|근무\s*장소)\s*[:：]\s*"
    r"(.{1,100}?)(?=\s+(?:역할|고용\s*형태|계약\s*기간|구분|\[조직\s*소개\])|$)",
    re.IGNORECASE,
)
_REGION_NAMES = {
    "서울": "Seoul",
    "인천": "Incheon",
    "대전": "Daejeon",
    "광주": "Gwangju",
    "대구": "Daegu",
    "부산": "Busan",
    "울산": "Ulsan",
}
_EMPLOYMENT_TYPES = {
    "BA002001": "full_time",
    "BA002002": "temporary",
    "BA002003": "internship",
    "BA002004": "temporary",
}


@dataclass(frozen=True, slots=True)
class _Variant:
    name: str
    host: str
    list_path: str
    detail_path: str
    public_job_path: str
    default_location: str


_VARIANTS = {
    "career.woowahan.com": _Variant(
        name="brothers",
        host="career.woowahan.com",
        list_path="/w1/recruits",
        detail_path="/w1/recruits/{id}",
        public_job_path="/recruitment/{id}/detail",
        default_location="South Korea",
    ),
    "career.woowayouths.com": _Variant(
        name="youths",
        host="career.woowayouths.com",
        list_path="/w1/recruits",
        detail_path="/w1/recruits/{id}",
        public_job_path="/recruitment/{id}/detail",
        default_location="South Korea",
    ),
    "bmart-career.woowayouths.com": _Variant(
        name="bmart",
        host="bmart-career.woowayouths.com",
        list_path="/w1/bmart/recruits",
        detail_path="/w1/bmart/recruits/{id}",
        public_job_path="/recruitment/detail/{id}",
        default_location="South Korea",
    ),
}


def _variant_from_url(url: str) -> _Variant | None:
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        return None
    return _VARIANTS.get((parsed.hostname or "").casefold())


def _api_url(variant: _Variant, path: str) -> str:
    return f"https://{variant.host}{path}"


async def _fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
) -> dict:
    response = await client.get(url, params=params, follow_redirects=True)
    if response.status_code in {404, 410}:
        raise LookupError(f"Woowa API endpoint is gone: {url}")
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Woowa response must be an object")
    return payload


def _payload_data(payload: dict, *, context: str) -> dict:
    data = payload.get("data")
    if payload.get("code") != "2000" or not isinstance(data, dict):
        raise ValueError(f"Woowa {context} response has invalid envelope")
    return data


def _listing_params(page: int) -> dict:
    return {
        "category": "all:all",
        "recruitCampaignSeq": 0,
        "all": "all",
        "page": page,
        "size": _PAGE_SIZE,
        "sort": "updateDate,desc",
    }


async def _fetch_listings(
    variant: _Variant, client: httpx.AsyncClient
) -> tuple[list[dict], bool]:
    url = _api_url(variant, variant.list_path)
    jobs: list[dict] = []
    seen: set[str] = set()
    expected_total: int | None = None
    page = 0

    while True:
        payload = await _fetch_json(
            client,
            url,
            params=_listing_params(page),
        )
        data = _payload_data(payload, context="listing")
        rows = data.get("list")
        total = data.get("totalSize")
        if not isinstance(rows, list) or not isinstance(total, int) or total < 0:
            raise ValueError("Woowa listing response has invalid list or totalSize")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise ValueError(
                f"Woowa listing total changed during pagination: {expected_total} -> {total}"
            )

        for raw in rows:
            if not isinstance(raw, dict):
                raise ValueError("Woowa listing response contains a non-object row")
            recruit_number = raw.get("recruitNumber")
            if not isinstance(recruit_number, str) or not _RECRUIT_NUMBER_RE.fullmatch(
                recruit_number
            ):
                raise ValueError("Woowa listing row has an invalid recruitNumber")
            if recruit_number in seen:
                raise ValueError(f"Woowa listing response duplicated {recruit_number!r}")
            seen.add(recruit_number)
            jobs.append(raw)

        if len(jobs) >= expected_total:
            break
        if not rows:
            raise ValueError(
                f"Woowa pagination stopped at {len(jobs)} of {expected_total} listings"
            )
        if len(jobs) >= _MAX_JOBS:
            return jobs[:_MAX_JOBS], True
        page += 1

    if len(jobs) != expected_total:
        raise ValueError(
            f"Woowa listing count mismatch: expected {expected_total}, got {len(jobs)}"
        )
    return jobs, False


async def _fetch_details(
    variant: _Variant,
    rows: list[dict],
    client: httpx.AsyncClient,
) -> list[dict]:
    semaphore = asyncio.Semaphore(_DETAIL_CONCURRENCY)

    async def fetch_one(row: dict) -> dict:
        recruit_number = row["recruitNumber"]
        url = _api_url(variant, variant.detail_path.format(id=recruit_number))
        async with semaphore:
            payload = await _fetch_json(client, url)
        detail = _payload_data(payload, context=f"detail {recruit_number}")
        if detail.get("recruitNumber") != recruit_number:
            raise ValueError(f"Woowa detail identity mismatch for {recruit_number!r}")
        return detail

    return list(await asyncio.gather(*(fetch_one(row) for row in rows)))


def _visible_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", value))).strip()


def _standard_locations(description: object, default: str) -> list[str]:
    match = _LOCATION_RE.search(_visible_text(description))
    if not match:
        return [default]
    raw = match.group(1).strip(" ,.;")
    if raw.startswith("전국"):
        return ["South Korea"]

    locations: list[str] = []
    for part in re.split(r"\s*(?:&|/|·)\s*", raw):
        part = part.strip(" ()")
        if not part:
            continue
        translated = _REGION_NAMES.get(part, part)
        locations.append(f"{translated}, South Korea")
    return locations or [default]


def _bmart_locations(detail: dict, listing: dict, default: str) -> list[str]:
    branches = detail.get("desiredBranches") or listing.get("desiredBranches")
    locations: list[str] = []
    if isinstance(branches, list):
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            remark = branch.get("recruitItemRemark")
            address = None
            if isinstance(remark, str):
                address = (parse_qs(remark).get("addr") or [None])[0]
            name = branch.get("recruitItemName")
            candidate = address or (name if isinstance(name, str) else None)
            if candidate and candidate.strip():
                locations.append(f"{candidate.strip()}, South Korea")
    if locations:
        return locations

    summary = listing.get("description")
    if isinstance(summary, str) and summary.strip():
        return [f"{summary.strip()}, South Korea"]
    return [default]


def _employment_type(detail: dict) -> str | None:
    raw = detail.get("employmentType")
    if not isinstance(raw, dict):
        return None
    code = raw.get("recruitItemCode")
    return _EMPLOYMENT_TYPES.get(code) if isinstance(code, str) else None


def _date(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.startswith(("2999-", "9999-")):
        return None
    match = _DATE_PREFIX_RE.match(candidate)
    if match is None:
        raise ValueError(f"Woowa response has an invalid date: {candidate!r}")
    try:
        return date.fromisoformat(match.group(1)).isoformat()
    except ValueError as exc:
        raise ValueError(f"Woowa response has an invalid date: {candidate!r}") from exc


def _bmart_description(detail: dict, listing: dict, locations: list[str]) -> str:
    title = html.escape(str(detail.get("recruitName") or listing.get("recruitName") or ""))
    employment = html.escape(_employment_type(detail) or "")
    location_text = html.escape("; ".join(locations))
    sections = [f"<h3>{title}</h3>", f"<p>Work location: {location_text}</p>"]
    if employment:
        sections.append(f"<p>Employment type: {employment}</p>")

    checklist = detail.get("applicantCheckList")
    items: list[str] = []
    if isinstance(checklist, list):
        for item in checklist:
            if not isinstance(item, dict):
                continue
            name = item.get("recruitItemName")
            remark = item.get("recruitItemRemark")
            if isinstance(name, str) and name.strip():
                text = name.strip()
                if isinstance(remark, str) and remark.strip():
                    text = f"{text} {remark.strip()}"
                items.append(f"<li>{html.escape(text)}</li>")
    if items:
        sections.append("<h3>Applicant information</h3><ul>" + "".join(items) + "</ul>")
    return "".join(sections)


def _parse_job(variant: _Variant, listing: dict, detail: dict) -> Job:
    recruit_number = detail["recruitNumber"]
    title = detail.get("recruitName") or listing.get("recruitName")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"Woowa detail {recruit_number!r} is missing recruitName")

    if variant.name == "bmart":
        locations = _bmart_locations(detail, listing, variant.default_location)
        description = _bmart_description(detail, listing, locations)
    else:
        description = detail.get("recruitContents")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"Woowa detail {recruit_number!r} is missing recruitContents")
        locations = _standard_locations(description, variant.default_location)

    metadata = {
        key: value
        for key, value in {
            "recruit_number": recruit_number,
            "corporation": detail.get("recruitCorporationNumber"),
            "career_type": detail.get("careerType"),
            "job_group": detail.get("jobGroup"),
        }.items()
        if value is not None
    }
    valid_through = _date(detail.get("recruitEndDate"))
    if valid_through:
        metadata["valid_through"] = valid_through

    return Job(
        url=_api_url(variant, variant.public_job_path.format(id=recruit_number)),
        title=title.strip(),
        description=description,
        locations=locations,
        employment_type=_employment_type(detail),
        date_posted=_date(detail.get("recruitOpenDate")),
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    variant = _variant_from_url(board.board_url)
    if variant is None:
        raise ValueError(f"Unsupported Woowa careers URL: {board.board_url!r}")

    rows, truncated = await _fetch_listings(variant, client)
    details = await _fetch_details(variant, rows, client)
    jobs = [_parse_job(variant, row, detail) for row, detail in zip(rows, details, strict=True)]
    return jobs[:_MAX_JOBS] if truncated else jobs
