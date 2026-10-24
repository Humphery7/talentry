from contextlib import nullcontext
from uuid import uuid4

import pytest

from fixtures import fixed_payload
from schemas.interview import Assessment
from services import interview_store
from services.interview_generation import (
    GenerationError,
    JobNotFound,
    _generate_valid_assessment,
    generate_assessment,
    normalize_payload,
)


class FakeConn:
    def __init__(self) -> None:
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def commit(self) -> None:
        pass

    def transaction(self):
        return nullcontext()


def test_normalize_makes_ids_and_types_safe() -> None:
    payload = fixed_payload()
    payload["sections"][0]["id"] = ""
    payload["sections"][0]["type"] = "BEHAVIOURAL"
    payload["sections"][0]["items"][0]["id"] = ""
    payload["sections"][0]["items"][0]["type"] = "TEXT_RESPONSE"
    payload["sections"][2]["items"][0]["resource"]["url"] = (
        "https://leetcode.com/problems/two-sum/description/"
    )

    normalized = normalize_payload(payload)

    assert normalized["sections"][0]["id"] == "section-1"
    assert normalized["sections"][0]["type"] == "behavioural"
    assert normalized["sections"][0]["items"][0]["id"] == "section-1-1"
    assert normalized["sections"][0]["items"][0]["type"] == "text_response"
    assert (
        normalized["sections"][2]["items"][0]["resource"]["url"]
        == "https://leetcode.com/problems/two-sum/"
    )


def test_generation_retries_once_then_succeeds(monkeypatch) -> None:
    calls: list[int] = []

    def fake(**kwargs):
        calls.append(1)
        return {"not": "an assessment"} if len(calls) == 1 else fixed_payload()

    monkeypatch.setattr("services.interview_generation.generate_json", fake)

    assessment = _generate_valid_assessment({"title": "Backend"}, None)

    assert assessment.title == "Backend Engineer Interview Prep"
    assert len(calls) == 2


def test_generation_stops_after_two_invalid_responses(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.interview_generation.generate_json",
        lambda **kwargs: {"not": "an assessment"},
    )

    with pytest.raises(GenerationError):
        _generate_valid_assessment({"title": "Backend"}, None)


def test_generate_reuses_the_latest_attempt_by_default(monkeypatch) -> None:
    existing_id = uuid4()
    monkeypatch.setattr(
        interview_store,
        "latest_attempt",
        lambda conn, user_id, job_id: {"id": existing_id},
    )
    generated = []
    monkeypatch.setattr(
        "services.interview_generation._generate_valid_assessment",
        lambda job, profile: generated.append(True),
    )

    attempt_id, created = generate_assessment(
        FakeConn(), user_id=uuid4(), job_id=1, new_attempt=False
    )

    assert attempt_id == existing_id
    assert created is False
    assert generated == []


def test_first_attempt_is_created_without_superseding(monkeypatch) -> None:
    assessment = Assessment.model_validate(fixed_payload())
    monkeypatch.setattr(
        interview_store, "latest_attempt", lambda conn, user_id, job_id: None
    )
    monkeypatch.setattr(
        interview_store,
        "load_job",
        lambda conn, job_id: {"id": job_id, "title": "Backend Engineer"},
    )
    monkeypatch.setattr(interview_store, "load_profile", lambda conn, user_id: None)
    monkeypatch.setattr(
        "services.interview_generation._generate_valid_assessment",
        lambda job, profile: assessment,
    )
    superseded: list[bool] = []
    monkeypatch.setattr(
        interview_store,
        "supersede_active",
        lambda conn, user_id, job_id: superseded.append(True),
    )
    monkeypatch.setattr(
        interview_store, "next_attempt_no", lambda conn, user_id, job_id: 1
    )
    new_id = uuid4()
    monkeypatch.setattr(
        interview_store,
        "insert_attempt",
        lambda conn, **kwargs: new_id,
    )

    attempt_id, created = generate_assessment(
        FakeConn(), user_id=uuid4(), job_id=7, new_attempt=False
    )

    assert attempt_id == new_id
    assert created is True
    assert superseded == []


def test_new_attempt_supersedes_and_saves(monkeypatch) -> None:
    assessment = Assessment.model_validate(fixed_payload())
    monkeypatch.setattr(
        interview_store, "latest_attempt", lambda conn, user_id, job_id: None
    )
    monkeypatch.setattr(
        interview_store,
        "load_job",
        lambda conn, job_id: {"id": job_id, "title": "Backend Engineer"},
    )
    monkeypatch.setattr(
        interview_store, "load_profile", lambda conn, user_id: None
    )
    monkeypatch.setattr(
        "services.interview_generation._generate_valid_assessment",
        lambda job, profile: assessment,
    )
    superseded: list[bool] = []
    monkeypatch.setattr(
        interview_store,
        "supersede_active",
        lambda conn, user_id, job_id: superseded.append(True),
    )
    monkeypatch.setattr(
        interview_store, "next_attempt_no", lambda conn, user_id, job_id: 3
    )
    new_id = uuid4()
    inserted: list[dict] = []

    def insert(conn, **kwargs):
        inserted.append(kwargs)
        return new_id

    monkeypatch.setattr(interview_store, "insert_attempt", insert)

    attempt_id, created = generate_assessment(
        FakeConn(), user_id=uuid4(), job_id=7, new_attempt=True
    )

    assert attempt_id == new_id
    assert created is True
    assert superseded == [True]
    assert inserted[0]["attempt_no"] == 3
    assert inserted[0]["title"] == "Backend Engineer Interview Prep"
    assert "sections" in inserted[0]["assessment_public"]
    assert "evaluation" not in inserted[0]["assessment_public"]["sections"][0]["items"][0]


def test_missing_job_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(
        interview_store, "latest_attempt", lambda conn, user_id, job_id: None
    )
    monkeypatch.setattr(interview_store, "load_job", lambda conn, job_id: None)

    with pytest.raises(JobNotFound):
        generate_assessment(
            FakeConn(), user_id=uuid4(), job_id=999, new_attempt=False
        )
