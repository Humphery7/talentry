from contextlib import nullcontext
from uuid import uuid4

import pytest

from fixtures import fixed_payload
from schemas.interview import Assessment
from services import interview_store
from services.interview_evaluation import (
    AttemptNotFound,
    InvalidAnswer,
    evaluate_answer,
)


class FakeConn:
    def commit(self) -> None:
        pass

    def transaction(self):
        return nullcontext()


def setup(monkeypatch):
    assessment = Assessment.model_validate(fixed_payload())
    saved: dict[str, dict] = {}

    monkeypatch.setattr(
        interview_store,
        "get_attempt",
        lambda conn, attempt_id, user_id: {
            "job_id": 1,
            "assessment_internal": assessment.model_dump(mode="json"),
        },
    )
    monkeypatch.setattr(
        interview_store,
        "load_job",
        lambda conn, job_id: {
            "title": "Backend Engineer",
            "company_name": "Acme",
            "seniority": "senior",
        },
    )

    def upsert(conn, **kwargs):
        saved[kwargs["item_id"]] = kwargs

    def list_responses(conn, attempt_id):
        return [
            {
                "item_id": item_id,
                "completed": row["completed"],
                "score": row["score"],
                "feedback": row["feedback"],
            }
            for item_id, row in saved.items()
        ]

    monkeypatch.setattr(interview_store, "upsert_response", upsert)
    monkeypatch.setattr(interview_store, "list_responses", list_responses)
    monkeypatch.setattr(
        interview_store, "update_attempt_progress", lambda *args, **kwargs: None
    )
    return assessment, saved


def attempt_args():
    return {
        "user_id": uuid4(),
        "attempt_id": uuid4(),
    }


def test_correct_multiple_choice_is_graded(monkeypatch) -> None:
    _, saved = setup(monkeypatch)
    args = attempt_args()

    result = evaluate_answer(
        FakeConn(),
        **args,
        item_id="s2-q1",
        answer={"selectedOptionId": "a"},
    )

    assert result["score"] == 100
    assert result["feedback"]["correct"] is True
    assert result["feedback"]["explanation"] == "HAVING filters after aggregation."
    assert result["progress"]["percent"] == 33
    assert saved["s2-q1"]["completed"] is True


def test_wrong_multiple_choice_reveals_the_key_after_submission(monkeypatch) -> None:
    setup(monkeypatch)
    args = attempt_args()

    result = evaluate_answer(
        FakeConn(),
        **args,
        item_id="s2-q1",
        answer={"selectedOptionId": "b"},
    )

    assert result["score"] == 0
    assert result["feedback"]["correct"] is False
    assert result["feedback"]["correctOptionId"] == "a"


def test_invalid_option_is_rejected(monkeypatch) -> None:
    setup(monkeypatch)
    args = attempt_args()

    with pytest.raises(InvalidAnswer):
        evaluate_answer(
            FakeConn(),
            **args,
            item_id="s2-q1",
            answer={"selectedOptionId": "z"},
        )


def test_external_practice_only_tracks_completion(monkeypatch) -> None:
    setup(monkeypatch)
    args = attempt_args()

    result = evaluate_answer(
        FakeConn(),
        **args,
        item_id="s3-q1",
        answer={"completed": True},
    )

    assert result["score"] is None
    assert result["completed"] is True
    assert result["progress"]["percent"] == 33
    assert result["progress"]["readiness"] is None


def test_written_answer_uses_the_rubric(monkeypatch) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(
        "services.interview_evaluation.generate_json",
        lambda **kwargs: {
            "score": 78,
            "strengths": ["Clear structure"],
            "weaknesses": ["Missed the outcome"],
            "improvements": ["End with a measurable result"],
        },
    )
    args = attempt_args()

    result = evaluate_answer(
        FakeConn(),
        **args,
        item_id="s1-q1",
        answer={"text": "I listened, proposed a compromise, and we shipped on time."},
    )

    assert result["score"] == 78
    assert result["feedback"]["strengths"] == ["Clear structure"]
    assert result["completed"] is True
    assert result["progress"]["percent"] == 33


def test_written_answer_is_saved_when_the_model_fails(monkeypatch) -> None:
    setup(monkeypatch)

    def fail(**kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr("services.interview_evaluation.generate_json", fail)
    args = attempt_args()

    result = evaluate_answer(
        FakeConn(),
        **args,
        item_id="s1-q1",
        answer={"text": "A real answer."},
    )

    assert result["score"] is None
    assert result["completed"] is True
    assert "error" in result["feedback"]
    assert result["progress"]["percent"] == 33


def test_attempt_must_belong_to_the_user(monkeypatch) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(
        interview_store, "get_attempt", lambda conn, attempt_id, user_id: None
    )
    args = attempt_args()

    with pytest.raises(AttemptNotFound):
        evaluate_answer(
            FakeConn(),
            **args,
            item_id="s2-q1",
            answer={"selectedOptionId": "a"},
        )
