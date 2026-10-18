"""Add labels to a job: seniority, occupation, technologies.

Plain keyword matching against the dictionaries in data/*.csv — no AI.

  seniority    looked up in the TITLE only ("Senior Engineer" -> senior).
               Descriptions say "senior" about everyone, so they would mislead.
  occupation   looked up in the TITLE. If several match, the longest wins
               ("Frontend Developer" beats plain "Developer").
  technologies looked up in the TITLE + DESCRIPTION.
"""

from __future__ import annotations

import html
import re

from talentry_crawler.models import Job, LabelDictionaries

# (label, phrase, must_match_exact_case)
_Term = tuple[str, str, bool]


def _plain_words(text: str) -> str:
    """'Sr. Software-Engineer (Remote)' -> ' Sr Software Engineer Remote '.

    Punctuation becomes spaces and both ends are padded, so checking
    `" senior " in title` only ever matches the whole word.
    """
    return " " + " ".join(re.findall(r"\w+", text)) + " "


def _html_to_text(markup: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", markup))


def _prepare_terms(terms_by_label: dict[str, list[str]]) -> list[_Term]:
    terms: list[_Term] = []
    for label, words in terms_by_label.items():
        for word in words:
            # Short ALL-CAPS words are acronyms (PM, QA, CEO): match them in exact case,
            # so "PO" doesn't match the Polish word "po".
            exact_case = word.isupper() and len(word) <= 4
            terms.append((label, _plain_words(word), exact_case))
    return terms


def _first_match(title_words: str, terms: list[_Term]) -> str | None:
    title_lower = title_words.lower()
    for label, term, exact_case in terms:
        if exact_case:
            if term in title_words:
                return label
        elif term.lower() in title_lower:
            return label
    return None


class Labeler:
    def __init__(self, dictionaries: LabelDictionaries) -> None:
        # Seniority: the CSV lists junior -> senior. Check the most senior first,
        # so "Senior Staff Engineer" is "staff", not "senior".
        most_senior_first = dict(reversed(list(dictionaries.seniority.items())))
        self._seniority = _prepare_terms(most_senior_first)

        # Occupations: longest phrase first, so the most specific one wins.
        self._occupations = sorted(
            _prepare_terms(dictionaries.occupations), key=lambda t: len(t[1]), reverse=True
        )

        # Technologies: for each one, the words to look for plus a regex that checks they
        # stand alone, e.g. (?<![A-Za-z0-9])(?:Node\.js|NodeJS)(?![A-Za-z0-9])
        self._technologies: list[tuple[str, list[str], bool, re.Pattern[str]]] = []
        for slug, patterns in dictionaries.technologies.items():
            if not patterns:
                continue
            exact_case = slug in dictionaries.case_sensitive_technologies
            alternatives = "|".join(re.escape(p) for p in sorted(patterns, key=len, reverse=True))
            regex = re.compile(
                rf"(?<![A-Za-z0-9])(?:{alternatives})(?![A-Za-z0-9])",
                0 if exact_case else re.IGNORECASE,
            )
            words = patterns if exact_case else [p.lower() for p in patterns]
            self._technologies.append((slug, words, exact_case, regex))

    def label(self, job: Job) -> None:
        """Fill in job.seniority, job.occupation and job.technologies."""
        title_words = _plain_words(job.title or "")
        job.seniority = _first_match(title_words, self._seniority)
        job.occupation = _first_match(title_words, self._occupations)

        text = f"{job.title or ''}\n{_html_to_text(job.description or '')}"
        text_lower = text.lower()
        found: list[str] = []
        for slug, words, exact_case, regex in self._technologies:
            haystack = text if exact_case else text_lower
            # Quick check first: only run the slower regex if one of the words appears at all.
            if any(word in haystack for word in words) and regex.search(text):
                found.append(slug)
        job.technologies = found
