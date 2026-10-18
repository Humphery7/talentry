"""Plain data shapes shared by every layer. No logic, no file or network access."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Company:
    """One employer (one row from data/companies.csv)."""

    slug: str
    name: str
    website: str | None = None
    logo_url: str | None = None
    icon_url: str | None = None
    industry: str | None = None
    employee_count_range: str | None = None
    founded_year: int | None = None


@dataclass(slots=True)
class Board:
    """One career page to crawl (one row from data/boards.csv)."""

    company_slug: str
    board_slug: str
    board_url: str
    monitor_type: str  # which ATS adapter reads it: "greenhouse", "ashby", "lever"
    monitor_config: dict[str, Any] = field(default_factory=dict)
    scraper_type: str | None = None
    scraper_config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Job:
    """One job posting, in the same shape no matter which ATS it came from."""

    url: str
    title: str | None = None
    description: str | None = None  # HTML
    locations: list[str] | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    date_posted: str | None = None
    salary: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    # Filled in by the labeling step (not by the ATS adapters):
    seniority: str | None = None  # e.g. "senior"
    occupation: str | None = None  # e.g. "frontend-developer"
    technologies: list[str] = field(default_factory=list)  # e.g. ["python", "aws"]


@dataclass(slots=True)
class LabelDictionaries:
    """The words the labeler looks for. Loaded from data/*.csv by the config layer.

    Each dict maps a label (slug) to the words/phrases that mean it.
    """

    seniority: dict[str, list[str]]  # "senior" -> ["Senior", "Sr", ...]  (junior -> senior order)
    occupations: dict[str, list[str]]  # "frontend-developer" -> ["Frontend Developer", ...]
    technologies: dict[str, list[str]]  # "python" -> ["Python"]
    case_sensitive_technologies: set[str]  # techs that must match exact case ("Java", "Rust")
