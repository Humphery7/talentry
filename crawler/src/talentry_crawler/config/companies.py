"""Load data/companies.csv (+ industries.csv to turn industry ids into names)."""

from __future__ import annotations

import csv
from pathlib import Path

from talentry_crawler.models import Company

from .paths import DATA_DIR


def _text(row: dict, key: str) -> str | None:
    return (row.get(key) or "").strip() or None


def _industry_names(data_dir: Path) -> dict[str, str]:
    with (data_dir / "industries.csv").open(newline="", encoding="utf-8") as f:
        return {row["id"]: row["name"] for row in csv.DictReader(f)}


def load_companies(data_dir: Path | None = None) -> list[Company]:
    data_dir = data_dir or DATA_DIR
    industries = _industry_names(data_dir)

    companies: list[Company] = []
    with (data_dir / "companies.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            founded = _text(row, "founded_year")
            companies.append(
                Company(
                    slug=row["slug"].strip(),
                    name=row["name"].strip(),
                    website=_text(row, "website"),
                    logo_url=_text(row, "logo_url"),
                    icon_url=_text(row, "icon_url"),
                    industry=industries.get(row.get("industry") or ""),
                    employee_count_range=_text(row, "employee_count_range"),
                    founded_year=int(founded) if founded and founded.isdigit() else None,
                )
            )
    return companies
