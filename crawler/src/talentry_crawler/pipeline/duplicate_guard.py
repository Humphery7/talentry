"""Keep an aggregator posting out of the database when the employer's own
board already has it.

JSearch hands back publisher links (Indeed, Jooble, LinkedIn, recruit.net), so
the same job has a different URL from the employer's career page and
`external_id` cannot see that it is the same posting.

Matching on the description is what once deleted 3,057 real Accenture
requisitions (their postings share identical text), so this guard is narrow on
purpose:

  * it only ever drops a row that carries its own employer (an aggregator row).
    A job from an employer's own ATS board is never touched here;
  * the employer must resolve to a company that is already in companies.csv
    (by slug, or by name with legal suffixes removed: "Scribd, Inc." -> scribd);
  * the title and one of the cities must be equal after normalisation;
  * and **exactly one** open job may match that company + title + city. When
    several match (Accenture has 1,004 "Custom Software Engineer" rows in
    Pune) there is no way to tell which requisition the aggregator copy is, so
    the copy is kept. A duplicate is cheaper than a lost job.

The aggregator pass runs after every employer board has been crawled (see
`crawl_boards`), so the comparison always sees today's postings.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from talentry_crawler.models import MONITORS_WITHOUT_CLOSE, Company, Job

# Only legal-form words, not descriptive ones: "Foo Systems" and "Foo" are not
# necessarily the same employer, and a wrong merger loses jobs.
_LEGAL_FORMS = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|gmbh|"
    r"plc|ag|sa|bv|nv|pty|pte|oy|ab|srl|spa|kk|kg)\b"
)
# JSearch titles often carry the publisher's decoration:
#   "Grainger is hiring: Software Engineer in Chicago"
#   "Junior Software Test Engineer (Java, AWS, SQL) - 897"
_HIRING_PREFIX = re.compile(r"^.*?\bis hiring:\s*")
_TRAILING_ID = re.compile(r"\s*[\-–—]\s*\d{1,5}\s*$")
_KEEP = re.compile(r"[^a-z0-9+#. ]+")
# Company names carry punctuation that never distinguishes two employers:
# "Scribd, Inc." and "Scribd Inc" are the same company.
_NAME_KEEP = re.compile(r"[^a-z0-9 ]+")


def normalize_name(name: str | None) -> str:
    """'Scribd, Inc.' -> 'scribd'. Used only to look a company up."""
    text = _NAME_KEEP.sub(" ", (name or "").lower())
    text = _LEGAL_FORMS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_title(title: str | None) -> str:
    text = (title or "").lower()
    text = _HIRING_PREFIX.sub("", text)
    text = _TRAILING_ID.sub("", text)
    text = _KEEP.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def cities(locations: Iterable[str] | None) -> set[str]:
    """'San Francisco, California' -> 'san francisco' (first part of each place)."""
    found: set[str] = set()
    for location in locations or []:
        city = str(location).split(",")[0].strip().lower()
        if city:
            found.add(city)
    return found


class EmployerIndex:
    """Which company slugs an aggregator posting's employer could be."""

    def __init__(self, companies: Iterable[Company]):
        self._by_name: dict[str, set[str]] = {}
        self._slugs: set[str] = set()
        for company in companies:
            self._slugs.add(company.slug)
            key = normalize_name(company.name)
            if key:
                self._by_name.setdefault(key, set()).add(company.slug)

    def resolve(self, job: Job) -> set[str]:
        slugs: set[str] = set()
        if job.company_slug in self._slugs:
            slugs.add(job.company_slug)
        slugs |= self._by_name.get(normalize_name(job.company_name), set())
        return slugs


def drop_employer_copies(
    jobs: list[Job], store, index: EmployerIndex
) -> tuple[list[Job], int]:
    """Split off the postings an employer board already has.

    Returns (kept jobs, how many were dropped). Never drops a board's own job:
    callers only pass aggregator rows (see `crawl_one_board`).
    """
    if not jobs:
        return jobs, 0

    resolved = [index.resolve(job) for job in jobs]
    slugs: set[str] = set().union(*resolved) if resolved else set()
    if not slugs:
        return jobs, 0

    # How many *employer* postings share each company + title + city. Aggregator
    # rows are not evidence: they are exactly what we are trying to avoid.
    seen: Counter[tuple[str, str, str]] = Counter()
    for row in store.open_postings(slugs):
        if row["monitor_type"] in MONITORS_WITHOUT_CLOSE:
            continue
        title = normalize_title(row["title"])
        if not title:
            continue
        for city in cities(row["locations"]):
            seen[(row["company_slug"], title, city)] += 1

    kept: list[Job] = []
    dropped = 0
    for job, job_slugs in zip(jobs, resolved):
        title = normalize_title(job.title)
        job_cities = cities(job.locations)
        if title and job_cities and any(
            seen.get((slug, title, city)) == 1
            for slug in job_slugs
            for city in job_cities
        ):
            dropped += 1
            continue
        kept.append(job)
    return kept, dropped
