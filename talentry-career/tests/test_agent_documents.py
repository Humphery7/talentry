from __future__ import annotations

from services.agent_applications import documents

CV = """SUMMARY
Frontend engineer with 5 years building React and TypeScript applications.

EXPERIENCE
Senior Frontend Engineer, Acme (2021-2024)
- Built a checkout flow in React and TypeScript.
- Led a team of 4 engineers.

EDUCATION
BSc Computer Science, University of Lagos (2015-2019)
"""

FACTS = {
    "full_name": "Ada Example",
    "email": "ada@example.com",
    "phone": "+1 555 0100",
    "location": "Lagos, Nigeria",
}


def source() -> str:
    return documents._source(CV, FACTS)


def test_accepts_a_preserved_cv_with_an_adjacent_framework() -> None:
    tailored = CV.replace(
        "React and TypeScript applications.",
        "React, Next.js and TypeScript applications.",
    )
    data = {
        "cv": tailored,
        "additions": [{"skill": "Next.js", "basis": "React"}],
    }
    assert documents.validate_cv(data, source(), CV) == []


def test_rejects_a_far_away_language() -> None:
    data = {"cv": CV + "\nSKILLS\nJava\n", "additions": []}
    problems = documents.validate_cv(data, source(), CV)
    assert any("Java" in problem for problem in problems)


def test_rejects_a_cv_that_loses_most_of_its_content() -> None:
    data = {"cv": "SUMMARY\nFrontend engineer.", "additions": []}
    problems = documents.validate_cv(data, source(), CV)
    assert any("much shorter" in problem for problem in problems)


def test_rejects_an_addition_that_is_not_in_the_cv_body() -> None:
    data = {
        "cv": CV,
        "additions": [{"skill": "Next.js", "basis": "React"}],
    }
    problems = documents.validate_cv(data, source(), CV)
    assert any("missing from the CV body" in problem for problem in problems)


def test_markdown_has_one_header_with_contact_details() -> None:
    body = "# Ada Example\n\n## Summary\nFrontend engineer."
    markdown = documents.cv_to_markdown(body, FACTS)
    assert markdown.count("# Ada Example") == 1
    assert "ada@example.com" in markdown
    assert "Lagos, Nigeria" in markdown


def test_original_cv_fallback_includes_contact_details() -> None:
    markdown = documents.original_cv_markdown(CV, FACTS)
    assert markdown.startswith("# Ada Example")
    assert "ada@example.com" in markdown
    assert "Senior Frontend Engineer" in markdown


BLOB = (
    "Dear Hiring Team, I am writing to express my interest in the Backend Engineer role. "
    "I build backend services in Python and TypeScript. "
    "In my last role I shipped FastAPI services to production. "
    "I also built data pipelines with AWS S3. "
    "My side projects include a voice journaling app. "
    "I would welcome the chance to discuss the role. "
    "Sincerely, Ada Example"
)


def test_single_blob_letter_becomes_spaced_paragraphs() -> None:
    letter = documents.format_letter(BLOB, FACTS)
    blocks = letter.strip().split("\n\n")
    assert blocks[0] == "Dear Hiring Team,"
    assert len(blocks) >= 4  # greeting, at least two paragraphs, sign-off
    assert blocks[-1] == "Sincerely,\nAda Example"
    assert "  " not in letter  # no run-on whitespace


def test_letter_is_left_alone_when_already_formatted() -> None:
    once = documents.format_letter(BLOB, FACTS)
    assert documents.format_letter(once, FACTS) == once


def test_letter_gets_a_greeting_and_sign_off_when_missing() -> None:
    letter = documents.format_letter(
        "I am interested in this role and have shipped Python services.", FACTS
    )
    assert letter.startswith("Dear Hiring Team,")
    assert letter.rstrip().endswith("Ada Example")
    assert "Sincerely," in letter


def test_letter_html_has_spaced_paragraphs_and_joined_sign_off() -> None:
    letter = documents.format_letter(BLOB, FACTS)
    html = documents.to_html(letter, letter=True)
    assert html.count("<p") >= 4
    assert "<p class='signoff'>Sincerely,<br>Ada Example</p>" in html
    assert "p{margin:0 0 11px}" in html
    assert "<h1" not in html


def test_cv_html_keeps_the_compact_style() -> None:
    html = documents.to_html(documents.original_cv_markdown(CV, FACTS))
    assert "<h1>Ada Example</h1>" in html
    assert "p{margin:3px 0}" in html
