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
