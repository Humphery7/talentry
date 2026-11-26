"""Saved career-coach filters, translated into SQL for the candidate query.

The coach page sends the same kind of filters as the jobs page (location
regions, level, industry, workplace, job type, roles, keywords). They are stored
per user and applied *before* the embedding top-N, so the whole pipeline — the
pgvector similarity search and the Gemini ranking — only sees eligible jobs.

Region definitions come from `shared/job-locations.json`, the same file the
TypeScript API reads, so "Europe" cannot drift between the two services.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import psycopg

# src/services/job_filters.py -> src -> talentry-career -> repo root.
_SHARED_FILE = (
    Path(__file__).resolve().parents[3] / "shared" / "job-locations.json"
)

with _SHARED_FILE.open(encoding="utf-8") as _fh:
    _SHARED = json.load(_fh)

REGIONS: dict[str, dict[str, Any]] = {
    region["slug"]: region for region in _SHARED["regions"]
}
# One alternation per region: far cheaper for Postgres than one pass per pattern.
REGION_PATTERNS: dict[str, str] = {
    slug: "(" + "|".join(region["patterns"]) + ")"
    for slug, region in REGIONS.items()
}
ALL_LOCATION_PATTERNS: list[str] = [
    pattern
    for region in _SHARED["regions"]
    for pattern in region["patterns"]
]
WORKPLACE_PATTERNS: dict[str, list[str]] = _SHARED["workplacePatterns"]

LIST_KEYS = ("loc", "lvl", "ind", "sch", "types", "roles")

# Same groups the jobs page shows, so "Senior level" means the same rows in both
# places.
LEVEL_GROUPS: dict[str, list[str]] = {
    "junior level": ["entry", "junior"],
    "mid level": ["mid"],
    "senior level": [
        "senior",
        "staff",
        "principal",
        "director",
        "lead",
        "executive",
    ],
}


def _normalize_workplace(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


# Region -> the exact location strings that belong to it. Built once from the
# distinct locations in the table and reused: comparing 4,500 strings by
# equality is far cheaper than regex-testing 127,000 mentions on every refresh.
_LOCATION_TTL_SECONDS = 600
_location_cache: tuple[float, dict[str, list[str]], list[str]] | None = None

_LOCATION_INDEX_SQL = """
WITH open_locs AS MATERIALIZED (
  SELECT DISTINCT loc.loc
  FROM jobs
  CROSS JOIN LATERAL jsonb_array_elements_text((jobs.locations_json)::jsonb) AS loc(loc)
  WHERE jobs.status = 'open' AND jobs.locations_json IS NOT NULL
)
SELECT DISTINCT l.loc, p.slug
FROM open_locs l
JOIN unnest(%s::text[], %s::text[]) AS p(slug, pattern)
  ON l.loc ~* p.pattern
"""


def location_index(
    conn: psycopg.Connection,
) -> tuple[dict[str, list[str]], list[str]]:
    """Return (region -> exact locations, every claimed location)."""
    global _location_cache
    now = time.monotonic()
    if _location_cache is not None:
        cached_at, by_region, all_locations = _location_cache
        if now - cached_at < _LOCATION_TTL_SECONDS:
            return by_region, all_locations

    slugs = list(REGIONS)
    patterns = [REGION_PATTERNS[slug] for slug in slugs]
    with conn.cursor() as cur:
        cur.execute(_LOCATION_INDEX_SQL, (slugs, patterns))
        rows = cur.fetchall()

    by_region: dict[str, list[str]] = {slug: [] for slug in slugs}
    for loc, slug in rows:
        by_region.setdefault(slug, []).append(loc)
    all_locations = sorted({loc for locs in by_region.values() for loc in locs})

    _location_cache = (now, by_region, all_locations)
    return by_region, all_locations


def normalize(raw: Any) -> dict[str, Any]:
    """Keep only known keys, coerce to short strings, drop empty values."""
    if not isinstance(raw, dict):
        return {}

    out: dict[str, Any] = {}
    for key in LIST_KEYS:
        value = raw.get(key)
        if isinstance(value, str):
            value = value.split(",")
        if not isinstance(value, list):
            continue
        items = [str(item).strip()[:80] for item in value if str(item).strip()]
        # dict.fromkeys keeps order while removing duplicates.
        items = list(dict.fromkeys(items))[:20]
        if items:
            out[key] = items

    keywords = raw.get("q")
    if isinstance(keywords, str) and keywords.strip():
        out["q"] = keywords.strip()[:120]

    return out


def build_where(
    filters: dict[str, Any] | None,
    region_locations: dict[str, list[str]] | None = None,
    all_locations: list[str] | None = None,
) -> tuple[str, list[Any]]:
    """Return (conditions, params); conditions is "" or "a AND b AND ..."."""
    filters = normalize(filters or {})
    conds: list[str] = []
    params: list[Any] = []

    def add(condition: str, *values: Any) -> None:
        conds.append(condition)
        params.extend(values)

    for key in ("loc", "lvl", "ind", "sch", "types", "roles", "q"):
        if key not in filters:
            continue

        if key == "loc":
            patterns: list[str] = []
            exact: list[str] = []
            likes: list[str] = []
            wants_other = False
            for value in filters[key]:
                slug = value.lower()
                if slug == "other":
                    # "Other" means: no region claims any of the job's locations.
                    wants_other = True
                elif slug in REGIONS:
                    known = (region_locations or {}).get(slug)
                    if known:
                        exact.extend(known)
                    else:
                        patterns.append(REGION_PATTERNS[slug])
                else:
                    # Free text, e.g. an old link with `loc=Berlin`.
                    likes.append(f"%{value}%")

            ors: list[str] = []
            if exact:
                ors.append(
                    "EXISTS (SELECT 1 FROM jsonb_array_elements_text("
                    "(jobs.locations_json)::jsonb) AS loc "
                    "WHERE loc = ANY(%s))"
                )
                params.append(exact)
            if patterns:
                ors.append(
                    "EXISTS (SELECT 1 FROM jsonb_array_elements_text("
                    "(jobs.locations_json)::jsonb) AS loc "
                    "WHERE loc ~* ANY(%s))"
                )
                params.append(patterns)
            if likes:
                ors.append(
                    "EXISTS (SELECT 1 FROM jsonb_array_elements_text("
                    "(jobs.locations_json)::jsonb) AS loc "
                    "WHERE loc ILIKE ANY(%s))"
                )
                params.append(likes)
            if wants_other:
                if all_locations:
                    ors.append(
                        "NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text("
                        "(jobs.locations_json)::jsonb) AS loc "
                        "WHERE loc = ANY(%s))"
                    )
                    params.append(all_locations)
                else:
                    ors.append(
                        "NOT EXISTS (SELECT 1 FROM jsonb_array_elements_text("
                        "(jobs.locations_json)::jsonb) AS loc "
                        "WHERE loc ~* ANY(%s))"
                    )
                    params.append(ALL_LOCATION_PATTERNS)
            if ors:
                conds.append("(" + " OR ".join(ors) + ")")

        elif key == "lvl":
            levels: list[str] = []
            for value in filters[key]:
                levels.extend(LEVEL_GROUPS.get(value.lower(), [value.lower()]))
            add("lower(jobs.seniority) = ANY(%s)", levels)

        elif key == "ind":
            add(
                "EXISTS (SELECT 1 FROM companies ic "
                "WHERE ic.slug = jobs.company_slug AND ic.industry ILIKE ANY(%s))",
                [f"%{value}%" for value in filters[key]],
            )

        elif key == "sch":
            workplaces = [_normalize_workplace(value) for value in filters[key]]
            ors = [
                "regexp_replace(lower(COALESCE(jobs.workplace_type, '')), "
                "'[^a-z0-9]+', '', 'g') = ANY(%s)"
            ]
            params.append(workplaces)
            location_patterns: list[str] = []
            for workplace in workplaces:
                location_patterns.extend(WORKPLACE_PATTERNS.get(workplace, []))
            if location_patterns:
                ors.append(
                    "EXISTS (SELECT 1 FROM jsonb_array_elements_text("
                    "(jobs.locations_json)::jsonb) AS loc "
                    "WHERE loc ILIKE ANY(%s))"
                )
                params.append(location_patterns)
            conds.append("(" + " OR ".join(ors) + ")")

        elif key == "types":
            add(
                "regexp_replace(lower(COALESCE(jobs.employment_type, '')), "
                "'[^a-z0-9]+', '', 'g') LIKE ANY(%s)",
                [
                    "%" + _normalize_workplace(value) + "%"
                    for value in filters[key]
                ],
            )

        elif key == "roles":
            add(
                "lower(jobs.occupation) = ANY(%s)",
                [value.lower() for value in filters[key]],
            )

        elif key == "q":
            like = f"%{filters[key]}%"
            add(
                "(jobs.title ILIKE %s OR EXISTS (SELECT 1 FROM companies qc "
                "WHERE qc.slug = jobs.company_slug AND qc.name ILIKE %s))",
                like,
                like,
            )

    return " AND ".join(conds), params


def describe(filters: dict[str, Any] | None) -> str:
    """A short human sentence for the ranking prompt, so reasons stay grounded."""
    filters = normalize(filters or {})
    if not filters:
        return ""
    parts: list[str] = []
    if labels := filters.get("loc"):
        parts.append(
            "locations: "
            + ", ".join(
                REGIONS[value.lower()]["label"]
                if value.lower() in REGIONS
                else value
                for value in labels
            )
        )
    for key, label in (
        ("lvl", "experience level"),
        ("ind", "industry"),
        ("sch", "workplace"),
        ("types", "job type"),
        ("roles", "role"),
    ):
        if values := filters.get(key):
            parts.append(f"{label}: {', '.join(values)}")
    if keywords := filters.get("q"):
        parts.append(f"keywords: {keywords}")
    return "The candidate asked to consider only jobs matching: " + "; ".join(
        parts
    ) + "."
