from __future__ import annotations

import io

from docx import Document

from services.agent_applications import docx_cv

FACTS = {"full_name": "Ada Example", "email": "ada@example.com"}

# Paragraph indexes in build_cv(): 0 name, 1 summary heading, 2 summary,
# 3 experience heading, 4 role line, 5 bullet, 6 skills heading, 7 skills.
SUMMARY = "Frontend engineer with five years of React experience."
BULLET = "Built a checkout flow in React and TypeScript."
ROLE = "Senior Frontend Engineer\t2021-2024"
SKILLS = "Languages: TypeScript, JavaScript"


def build_cv() -> bytes:
    document = Document()
    document.add_heading("ADA EXAMPLE", level=1)
    document.add_heading("PROFESSIONAL SUMMARY", level=2)
    document.add_paragraph(SUMMARY)
    document.add_heading("EXPERIENCE", level=2)
    role = document.add_paragraph()
    role.add_run("Senior Frontend Engineer").bold = True
    role.add_run("\t2021-2024")
    document.add_paragraph(BULLET, style="List Paragraph")
    document.add_heading("TECHNICAL SKILLS", level=2)
    document.add_paragraph(SKILLS)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def test_only_summary_bullets_and_skills_are_editable() -> None:
    document = Document(io.BytesIO(build_cv()))
    slots = docx_cv.editable_slots(document)
    assert [(slot.index, slot.kind) for slot in slots] == [
        (2, "summary"),
        (5, "bullet"),
        (7, "skills"),
    ]


def test_rewriting_a_bullet_keeps_the_rest_of_the_document() -> None:
    edited = docx_cv.apply_edits(build_cv(), {5: "Shipped a React checkout flow."})
    text = docx_cv.plain_text(edited)
    assert "Shipped a React checkout flow." in text
    assert BULLET not in text
    # The role line and its tab stop are untouched.
    assert ROLE in text
    assert SKILLS in text


def test_rejects_a_far_language_and_a_missing_index() -> None:
    document = Document(io.BytesIO(build_cv()))
    slots = docx_cv.editable_slots(document)
    edits, problems = docx_cv.validate_edits(
        {
            "edits": [
                {"index": 2, "text": "Frontend engineer who also writes Java services."},
                {"index": 4, "text": "Rewrite of a line the model may not touch."},
            ]
        },
        slots,
        SUMMARY + " " + BULLET,
    )
    assert edits == {}
    assert any("Java" in problem for problem in problems)


def test_rejects_a_rewrite_that_grows_too_much() -> None:
    document = Document(io.BytesIO(build_cv()))
    slots = docx_cv.editable_slots(document)
    edits, problems = docx_cv.validate_edits(
        {"edits": [{"index": 5, "text": BULLET + " with many more words " * 10}]},
        slots,
        SUMMARY,
    )
    assert edits == {}
    assert any("much longer" in problem for problem in problems)


def test_keeps_the_safe_rewrites_when_another_is_rejected() -> None:
    document = Document(io.BytesIO(build_cv()))
    slots = docx_cv.editable_slots(document)
    edits, problems = docx_cv.validate_edits(
        {
            "edits": [
                {"index": 2, "text": "Frontend engineer focused on React and TypeScript."},
                {"index": 5, "text": "Built a checkout flow in Java."},
            ]
        },
        slots,
        SUMMARY + " " + BULLET,
    )
    assert list(edits) == [2]
    assert any("Java" in problem for problem in problems)


def test_accepts_a_grounded_rewrite() -> None:
    document = Document(io.BytesIO(build_cv()))
    slots = docx_cv.editable_slots(document)
    edits, problems = docx_cv.validate_edits(
        {"edits": [{"index": 5, "text": "Built a React checkout flow in TypeScript."}]},
        slots,
        SUMMARY + " " + BULLET + " " + SKILLS,
    )
    assert problems == []
    assert edits == {5: "Built a React checkout flow in TypeScript."}


def test_is_template_rejects_junk() -> None:
    assert docx_cv.is_template(build_cv()) is True
    assert docx_cv.is_template(b"not a docx") is False


def test_missing_libreoffice_is_a_template_error(monkeypatch) -> None:
    def missing() -> str:
        raise docx_cv.TemplateError("LibreOffice is not installed")

    monkeypatch.setattr(docx_cv, "_soffice", missing)
    try:
        docx_cv.to_pdf(build_cv())
    except docx_cv.TemplateError:
        return
    raise AssertionError("expected TemplateError")


def test_rewrites_that_spill_to_a_second_page_are_reverted(monkeypatch) -> None:
    template = build_cv()
    long_bullet = "Built a checkout flow in React and TypeScript for every region."
    monkeypatch.setattr(docx_cv, "_soffice", lambda: "soffice")
    monkeypatch.setattr(
        docx_cv,
        "_generate",
        lambda *args, **kwargs: (
            {2: "Frontend engineer focused on React.", 5: long_bullet, 7: "Languages: TypeScript"},
            [],
            [],
        ),
    )

    def fake_pdf(data: bytes) -> bytes:
        return b"two" if "every region" in docx_cv.plain_text(data) else b"one"

    monkeypatch.setattr(docx_cv, "to_pdf", fake_pdf)
    monkeypatch.setattr(docx_cv, "page_count", lambda pdf: 2 if pdf == b"two" else 1)

    result = docx_cv.tailor(template, FACTS, SUMMARY, {"title": "Frontend Engineer"})

    text = result.content
    assert "every region" not in text  # the long bullet was given back
    assert "Frontend engineer focused on React." in text
    assert any("Reverted 1 rewrite" in note for note in result.notes)
    assert result.pdf == b"one"
    assert result.pages == 1
