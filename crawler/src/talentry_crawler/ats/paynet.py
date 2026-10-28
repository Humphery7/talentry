"""Pay-Net — GET https://api.pay-netonline.com/applicantpublic/jobpostings."""

from __future__ import annotations

import html
import re
from datetime import datetime
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import UUID

import httpx

from talentry_crawler.models import Board, Job

_API_URL = "https://api.pay-netonline.com/applicantpublic/jobpostings"
_COMPANY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def company_from_url(board_url: str) -> str | None:
    try:
        parsed = urlparse(board_url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "www.pay-netonline.com"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.path.casefold() != "/paynet/applicant/postings.aspx"
    ):
        return None
    company = parse_qs(parsed.query).get("co", [None])[0]
    if not isinstance(company, str) or not _COMPANY_RE.fullmatch(company):
        return None
    return company


def _job_url(posting_id: str) -> str:
    return (
        "https://www.pay-netonline.com/PayNet/Applicant/Posting.aspx?"
        + urlencode({"JobPostingID": posting_id})
    )


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _html_fragment(value: object) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    if "<" in cleaned and ">" in cleaned:
        return cleaned
    return f"<p>{html.escape(cleaned).replace(chr(10), '<br>')}</p>"


def _canonical_uuid(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _describe(position: dict) -> tuple[str | None, str | None]:
    summary = _html_fragment(position.get("Description")) or _html_fragment(position.get("Text"))
    requirements = _html_fragment(position.get("Requirements"))
    sections = [part for part in (summary, requirements) if part]
    if summary and requirements:
        sections[1] = f"<h3>Requirements</h3>\n{requirements}"
    return "\n".join(sections) or None, requirements


def _iso_date(value: object) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    for date_format in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_job(raw: object, company_id: str) -> Job | None:
    if not isinstance(raw, dict):
        return None
    posting_id = _canonical_uuid(raw.get("ID"))
    position = raw.get("Position")
    if posting_id is None or not isinstance(position, dict):
        return None

    title = _clean_text(position.get("Title"))
    description, requirements = _describe(position)
    if title is None or description is None:
        return None

    company = raw.get("Company")
    company_name = _clean_text(company.get("Name")) if isinstance(company, dict) else None
    valid_through = _iso_date(position.get("EndDate"))
    metadata = {
        key: value
        for key, value in {
            "posting_id": posting_id,
            "company_id": company_id,
            "company_name": company_name,
            "valid_through": valid_through,
        }.items()
        if value not in (None, "")
    }
    if requirements:
        metadata["qualifications"] = requirements

    return Job(
        url=_job_url(posting_id),
        title=title,
        description=description,
        locations=[value] if (value := _clean_text(position.get("Location"))) else None,
        date_posted=_iso_date(position.get("StartDate")),
        metadata=metadata,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    company_id = board.monitor_config.get("company_id") or company_from_url(board.board_url)
    if not isinstance(company_id, str) or not _COMPANY_RE.fullmatch(company_id):
        raise ValueError(
            f"Cannot derive Pay-Net company from {board.board_url!r} "
            "and no company_id in monitor_config"
        )

    response = await client.get(
        _API_URL,
        params={"company_id": company_id},
        headers={"Accept": "application/json"},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(
            f"Pay-Net company {company_id!r} returned {response.status_code} (board gone)"
        )
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Pay-Net response must be a list")

    jobs: list[Job] = []
    seen_ids: set[str] = set()
    for raw in payload:
        job = _parse_job(raw, company_id)
        if job is None:
            continue
        posting_id = str((job.metadata or {}).get("posting_id"))
        if posting_id in seen_ids:
            continue
        seen_ids.add(posting_id)
        jobs.append(job)
    return jobs
