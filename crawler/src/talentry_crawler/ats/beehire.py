"""Beehire — GET https://app.beehire.com/users/getPublicCampaigns/{slug}."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx

from talentry_crawler.models import Board, Job

_HOST = "app.beehire.com"
_ORIGIN = f"https://{_HOST}"
_SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,127}", re.IGNORECASE)
_LANGUAGES = {
    "0": "en",
    "1": "fr",
    "2": "nl",
    "3": "de",
    "4": "pt",
    "5": "es",
    "6": "it",
}
_WORKPLACE_TYPES = {
    "remotework_none": "onsite",
    "remotework_onsite": "onsite",
    "remotework_hybrid": "hybrid",
    "remotework_remote": "remote",
}
_CONTRACT_TYPES = {
    "contracttype_permanent": "permanent",
    "contracttype_fixedterm": "fixed-term",
    "contracttype_temporary": "temporary",
    "contracttype_internship": "internship",
    "contracttype_freelance": "freelance",
}
_CONTRACT_DURATIONS = {
    "contractduration_fulltime": "full-time",
    "contractduration_parttime": "part-time",
    "contractduration_internship": "internship",
}


def slug_from_url(board_url: str) -> str | None:
    parsed = urlparse(board_url)
    if (parsed.hostname or "").casefold() != _HOST:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0].casefold() not in {"career", "careerrss"}:
        return None
    slug = parts[1]
    return slug.lower() if _SLUG_RE.fullmatch(slug) else None


def _api_url(slug: str) -> str:
    return f"{_ORIGIN}/users/getPublicCampaigns/{slug}"


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _localized_value(value: object, language: object = None) -> str | None:
    if isinstance(value, str):
        return _clean_text(value)
    if not isinstance(value, dict):
        return None
    preferred = str(language) if language is not None else None
    for key in (preferred, "0"):
        if key is not None:
            candidate = _clean_text(value.get(key))
            if candidate:
                return candidate
    for candidate in value.values():
        cleaned = _clean_text(candidate)
        if cleaned:
            return cleaned
    return None


def _locations(raw: dict) -> list[str] | None:
    location = raw.get("location")
    if not isinstance(location, dict):
        return None
    name = _clean_text(location.get("name"))
    if name:
        return [name]
    if location.get("isWorldwide") is True:
        return ["Worldwide"]
    parts = [
        part
        for key in ("city", "state", "country")
        if (part := _clean_text(location.get(key))) is not None
    ]
    return [", ".join(dict.fromkeys(parts))] if parts else None


def _job_url(raw: dict) -> str | None:
    link = _clean_text(raw.get("inviteLink"))
    if link:
        return urljoin(f"{_ORIGIN}/", link)
    key = _clean_text(raw.get("inviteKey"))
    return f"{_ORIGIN}/invite/{key}" if key else None


def _contract(raw: dict) -> tuple[str | None, str | None]:
    details = raw.get("details")
    contract = details.get("contract") if isinstance(details, dict) else None
    if not isinstance(contract, dict):
        return None, None
    contract_type = _clean_text(contract.get("type"))
    duration = _clean_text(contract.get("duration"))
    employment_type = _CONTRACT_TYPES.get(contract_type.casefold()) if contract_type else None
    if employment_type is None and duration:
        employment_type = _CONTRACT_DURATIONS.get(duration.casefold(), duration)
    remote = _clean_text(contract.get("remote"))
    workplace_type = _WORKPLACE_TYPES.get(remote.casefold()) if remote else None
    return employment_type, workplace_type


def _parse_job(raw: dict) -> Job | None:
    url = _job_url(raw)
    language = raw.get("language")
    title = _localized_value(raw.get("title"), language)
    if not url or not title:
        return None

    description = _localized_value(raw.get("fullDescription"), language)
    if description is None:
        description = _localized_value(raw.get("description"), language)
    employment_type, workplace_type = _contract(raw)

    categories = raw.get("jobCategories")
    category_names = [
        item.get("label")
        for item in categories
        if isinstance(item, dict) and _clean_text(item.get("label"))
    ] if isinstance(categories, list) else []

    metadata = {
        key: value
        for key, value in {
            "id": raw.get("id") or raw.get("_id"),
            "invite_key": raw.get("inviteKey"),
            "deadline": raw.get("deadline"),
            "categories": category_names or None,
        }.items()
        if value not in (None, "", [])
    }

    return Job(
        url=url,
        title=title,
        description=description,
        locations=_locations(raw),
        employment_type=employment_type,
        workplace_type=workplace_type,
        metadata=metadata or None,
    )


async def discover(board: Board, client: httpx.AsyncClient) -> list[Job]:
    slug = board.monitor_config.get("slug") or slug_from_url(board.board_url)
    if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
        raise ValueError(
            f"Cannot derive Beehire slug from {board.board_url!r} "
            "and no slug in monitor_config"
        )
    slug = slug.lower()

    response = await client.get(
        _api_url(slug),
        headers={"Accept": "application/json", "Referer": f"{_ORIGIN}/career/{slug}"},
        follow_redirects=True,
    )
    if response.status_code in {404, 410}:
        raise LookupError(f"Beehire board {slug!r} returned {response.status_code} (board gone)")
    response.raise_for_status()

    payload = response.json()
    campaigns = payload.get("campaigns") if isinstance(payload, dict) else None
    if not isinstance(campaigns, list):
        raise ValueError("Beehire response must contain a campaigns list")

    return [
        job
        for raw in campaigns
        if isinstance(raw, dict) and (job := _parse_job(raw)) is not None
    ]
