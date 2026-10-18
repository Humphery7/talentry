"""Load the label dictionaries (seniority, occupations, technologies) from data/*.csv.

These CSVs are the words the labeling step searches for. Edit the CSV to teach the
labeler something new — no code change needed.
"""

from __future__ import annotations

import csv
from pathlib import Path

from talentry_crawler.models import LabelDictionaries

from .paths import DATA_DIR

# "Executive" on its own is also everyday job-title language ("Account Executive"),
# so for these labels we trust only the aliases column (CEO, CTO, Managing Director...).
ALIASES_ONLY = {"executive"}

# Columns that are NOT a name in some language.
_NOT_NAMES = {"slug", "parent", "domain", "aliases"}


def _read_terms(path: Path) -> dict[str, list[str]]:
    """slug -> every name (all languages) and alias for it. Row order is kept."""
    terms: dict[str, list[str]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            slug = row["slug"]
            words = [w for w in (row.get("aliases") or "").split("|") if w.strip()]
            if slug not in ALIASES_ONLY:
                words += [v for k, v in row.items() if k not in _NOT_NAMES and v and v.strip()]
            terms[slug] = [w.strip() for w in words]
    return terms


def _read_technologies(path: Path) -> tuple[dict[str, list[str]], set[str]]:
    patterns: dict[str, list[str]] = {}
    case_sensitive: set[str] = set()
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            patterns[row["slug"]] = [p.strip() for p in row["patterns"].split("|") if p.strip()]
            if "cs" in (row.get("flags") or ""):
                case_sensitive.add(row["slug"])
    return patterns, case_sensitive


def load_label_dictionaries(data_dir: Path | None = None) -> LabelDictionaries:
    data_dir = data_dir or DATA_DIR
    technologies, case_sensitive = _read_technologies(data_dir / "technologies.csv")
    return LabelDictionaries(
        seniority=_read_terms(data_dir / "seniority.csv"),
        occupations=_read_terms(data_dir / "occupations.csv"),
        technologies=technologies,
        case_sensitive_technologies=case_sensitive,
    )
