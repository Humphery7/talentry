import pytest
from pydantic import ValidationError

from fixtures import fixed_payload
from schemas.interview import Assessment, compute_progress, public_assessment


def test_valid_assessment_parses() -> None:
    assessment = Assessment.model_validate(fixed_payload())
    assert assessment.title == "Backend Engineer Interview Prep"
    assert len(assessment.sections) == 3


def test_public_assessment_hides_keys_and_rubrics() -> None:
    assessment = Assessment.model_validate(fixed_payload())
    public = public_assessment(assessment)

    mcq = public["sections"][1]["items"][0]
    assert "evaluation" not in mcq
    assert "correct_option_id" not in mcq
    assert mcq["options"][0]["text"] == "HAVING"

    written = public["sections"][0]["items"][0]
    assert "evaluation" not in written


def test_duplicate_item_ids_are_rejected() -> None:
    payload = fixed_payload()
    payload["sections"][1]["items"][0]["id"] = "s1-q1"

    with pytest.raises(ValidationError, match="item ids must be unique"):
        Assessment.model_validate(payload)


def test_multiple_choice_needs_a_valid_answer_key() -> None:
    payload = fixed_payload()
    payload["sections"][1]["items"][0]["evaluation"]["correct_option_id"] = "z"

    with pytest.raises(ValidationError, match="correct_option_id"):
        Assessment.model_validate(payload)


def test_multiple_choice_needs_an_explanation() -> None:
    payload = fixed_payload()
    payload["sections"][1]["items"][0]["evaluation"]["explanation"] = ""

    with pytest.raises(ValidationError, match="explanation"):
        Assessment.model_validate(payload)


def test_written_items_need_a_rubric() -> None:
    payload = fixed_payload()
    payload["sections"][0]["items"][0]["evaluation"]["rubric"] = []

    with pytest.raises(ValidationError, match="rubric"):
        Assessment.model_validate(payload)


def test_leetcode_links_must_be_canonical() -> None:
    payload = fixed_payload()
    payload["sections"][2]["items"][0]["resource"]["url"] = (
        "https://example.com/problems/two-sum/"
    )

    with pytest.raises(ValidationError, match="LeetCode links"):
        Assessment.model_validate(payload)


def test_progress_and_readiness() -> None:
    assessment = Assessment.model_validate(fixed_payload())

    empty = compute_progress(assessment, [])
    assert empty["percent"] == 0
    assert empty["readiness"] is None
    assert empty["totalItems"] == 3

    partial = compute_progress(
        assessment,
        [
            {"item_id": "s1-q1", "completed": True, "score": 80},
            {"item_id": "s2-q1", "completed": True, "score": 100},
        ],
    )
    assert partial["percent"] == 67
    assert partial["readiness"] is None

    complete = compute_progress(
        assessment,
        [
            {"item_id": "s1-q1", "completed": True, "score": 80},
            {"item_id": "s2-q1", "completed": True, "score": 100},
            {"item_id": "s3-q1", "completed": True, "score": None},
        ],
    )
    assert complete["percent"] == 100
    assert complete["readiness"] == 90
    assert complete["sections"][2]["percent"] == 100
