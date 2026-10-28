"""Personal facts and the rules for what the agent may never guess."""

from __future__ import annotations

import re
from typing import Any

FACT_KEYS = (
    "full_name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "location",
    "current_title",
    "current_company",
    "years_experience",
    "headline",
    "linkedin_url",
    "github_url",
    "website_url",
)

ASKED_FACTS = (
    "phone",
    "linkedin_url",
    "github_url",
    "website_url",
    "current_company",
)


def normalize(text: str | None) -> str:
    value = (text or "").lower().replace("*", " ").replace("✱", " ")
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


_SENSITIVE: list[tuple[str, re.Pattern[str]]] = [
    (
        "work authorization",
        re.compile(
            r"authori[sz]ed to work|work authori[sz]ation|right to work|"
            r"legally (able|eligible|entitled|permitted)|eligible to work|"
            r"work permit|work visa|\bvisa\b|sponsor|immigration|"
            r"employment eligibility|citizen|nationality"
        ),
    ),
    (
        "legal declaration",
        re.compile(
            r"convict|criminal|felony|background (check|screen)|drug test|"
            r"conflict of interest|non[- ]?compete|restrictive covenant|"
            r"\bi (agree|certify|acknowledge|confirm|consent|have read|understand)\b|"
            r"\bconsent\b|\backnowledge|terms (and|of)|privacy (policy|notice)|"
            r"gdpr|data (processing|protection)|\bagree\b|\bdeclar|under oath|"
            r"accurate and complete"
        ),
    ),
    (
        "demographic",
        re.compile(
            r"gender|\bsex\b|\brace\b|racial|ethnic|hispanic|latino|veteran|"
            r"military|disabilit|disabled|pronoun|sexual orientation|lgbt|"
            r"transgender|religio|marital|date of birth|\bdob\b|\bage\b|birth|"
            r"self[- ]identif|equal opportunity|eeo"
        ),
    ),
    (
        "compensation",
        re.compile(
            r"salary|compensation|pay (expectation|range)|expected pay|"
            r"desired (pay|rate)|rate expectation|remuneration"
        ),
    ),
    (
        "availability",
        re.compile(
            r"notice period|start date|available to start|earliest (start|you can)|"
            r"when can you start|relocat"
        ),
    ),
]

_PERSONAL_LABEL = re.compile(
    r"\bname\b|e-?mail|phone|mobile|telephone|address|linkedin|github|website|"
    r"portfolio|\burl\b|\bcity\b|\bcountry\b|\bstate\b|zip|postal|location|pronoun"
)


def classify(label: str, context: str = "") -> str | None:
    text = normalize(f"{label} {context}")
    for category, pattern in _SENSITIVE:
        if pattern.search(text):
            return category
    return None


def is_personal_label(label: str) -> bool:
    return bool(_PERSONAL_LABEL.search(normalize(label)))


_FACT_LABELS: list[tuple[str, re.Pattern[str]]] = [
    ("first_name", re.compile(r"^(your )?(first|given) name$")),
    ("last_name", re.compile(r"^(your )?(last|family|sur) ?name$")),
    ("full_name", re.compile(r"^(your )?(full |legal )?name$")),
    ("email", re.compile(r"^(your )?(preferred |contact )?e ?mail( address)?$")),
    ("phone", re.compile(r"^(your )?(phone|mobile|telephone|cell)( number)?$")),
    ("linkedin_url", re.compile(r"^(your )?linkedin( profile| url)?$")),
    ("github_url", re.compile(r"^(your )?(github|git hub)( profile| url)?$")),
    (
        "website_url",
        re.compile(
            r"^(your )?(website|personal (website|site)|portfolio( url| link)?|"
            r"personal url)$"
        ),
    ),
    ("current_company", re.compile(r"^(current|present) (company|employer)$")),
    (
        "location",
        re.compile(r"^(your )?(current )?(location|city)( city)?$"),
    ),
]


def fact_for_label(label: str) -> str | None:
    text = normalize(label)
    for key, pattern in _FACT_LABELS:
        if pattern.match(text):
            return key
    return None


def build_facts(
    user: dict[str, Any],
    profile: dict[str, Any] | None,
    bank: dict[str, dict[str, Any]],
) -> dict[str, str]:
    profile = profile or {}
    facts: dict[str, str] = {}

    name = (user.get("name") or "").strip()
    if name:
        parts = name.split()
        facts["full_name"] = name
        facts["first_name"] = parts[0]
        if len(parts) > 1:
            facts["last_name"] = " ".join(parts[1:])
    if user.get("email"):
        facts["email"] = user["email"]

    for source, key in (
        ("location", "location"),
        ("current_title", "current_title"),
        ("headline", "headline"),
    ):
        value = (profile.get(source) or "").strip()
        if value:
            facts[key] = value
    if profile.get("years_experience") is not None:
        facts["years_experience"] = str(profile["years_experience"])

    for key in FACT_KEYS:
        saved = bank.get(f"fact:{key}")
        if saved and (saved.get("answer") or "").strip():
            facts[key] = saved["answer"].strip()
    return facts


def readiness(
    profile: dict[str, Any] | None,
) -> list[str]:
    missing: list[str] = []
    if not profile or not (profile.get("cv_data") or "").strip():
        missing.append("Upload your CV in your profile.")
    if not profile or not any(
        (profile.get(key) or "").strip()
        for key in ("headline", "current_title", "summary")
    ):
        missing.append("Add a headline, current title or summary to your profile.")
    return missing


_NUMBER = re.compile(r"[$€£]?\d[\d,.]*\s?(?:%|k|m|bn)?", re.IGNORECASE)


def ungrounded_numbers(text: str, *sources: str) -> list[str]:
    haystack = normalize(" ".join(sources)).replace(" ", "")
    haystack_raw = " ".join(sources).lower().replace(",", "")
    bad: list[str] = []
    for match in _NUMBER.finditer(text):
        token = match.group().strip().rstrip(".,")
        digits = re.sub(r"\D", "", token)
        if len(digits) < 2 and not re.search(r"[%$€£]", token):
            continue
        plain = token.lower().replace(",", "").replace(" ", "")
        if (
            plain in haystack_raw.replace(" ", "")
            or normalize(token).replace(" ", "") in haystack
        ):
            continue
        bad.append(token)
    return sorted(set(bad))
