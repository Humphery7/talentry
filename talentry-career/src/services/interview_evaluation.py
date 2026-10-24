"""Grade or evaluate a single interview answer and update progress."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import psycopg
from pydantic import BaseModel, Field

from schemas.interview import (
    MAX_RESPONSE_TEXT,
    Assessment,
    Item,
    ItemType,
    compute_progress,
    find_item,
)
from services import interview_store
from services.gemini import generate_json

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are an experienced interviewer grading one written answer.
Use only the job, the question and the rubric provided. Be specific and fair.
Return JSON that matches the requested schema."""

EVALUATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "improvements": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "strengths", "weaknesses", "improvements"],
}


class EvaluationResult(BaseModel):
    score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class AttemptNotFound(RuntimeError):
    pass


class ItemNotFound(RuntimeError):
    pass


class InvalidAnswer(ValueError):
    pass


def _feedback_error() -> dict[str, Any]:
    return {
        "error": "Could not evaluate this answer right now. Your answer was saved.",
    }


def _evaluate_written(
    item: Item,
    answer_text: str,
    job: dict[str, Any] | None,
) -> tuple[int | None, dict[str, Any]]:
    rubric = "\n".join(
        f"- {criterion.criterion} (weight {criterion.weight}): {criterion.description}"
        for criterion in item.evaluation.rubric
    )
    prompt = f"""JOB
Title: {(job or {}).get("title") or "Unspecified"}
Company: {(job or {}).get("company_name") or "Unspecified"}
Seniority: {(job or {}).get("seniority") or "Unspecified"}

QUESTION
{item.question}

INSTRUCTIONS
{item.instructions or "None"}

RUBRIC
{rubric}

CANDIDATE ANSWER
{answer_text}

Score the answer from 0 to 100 against the rubric. Return 2-4 short strengths,
weaknesses and concrete improvements."""

    try:
        payload = generate_json(
            input=prompt,
            system_instruction=SYSTEM_INSTRUCTION,
            schema=EVALUATION_SCHEMA,
        )
        result = EvaluationResult.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - the saved answer must survive
        logger.exception("Could not evaluate interview answer: %s", exc)
        return None, _feedback_error()

    feedback = {
        "score": result.score,
        "strengths": result.strengths[:5],
        "weaknesses": result.weaknesses[:5],
        "improvements": result.improvements[:5],
    }
    return result.score, feedback


def _grade_multiple_choice(item: Item, answer: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    selected = answer.get("selectedOptionId")
    if not isinstance(selected, str) or selected not in {
        option.id for option in item.options
    }:
        raise InvalidAnswer("selectedOptionId must match one of the options.")

    correct = selected == item.evaluation.correct_option_id
    score = 100 if correct else 0
    feedback = {
        "correct": correct,
        "score": score,
        "correctOptionId": item.evaluation.correct_option_id,
        "explanation": item.evaluation.explanation,
    }
    return score, feedback


def evaluate_answer(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    attempt_id: UUID,
    item_id: str,
    answer: dict[str, Any],
) -> dict[str, Any]:
    attempt = interview_store.get_attempt(conn, attempt_id, user_id)
    if attempt is None:
        raise AttemptNotFound("Interview attempt not found.")

    assessment = Assessment.model_validate(attempt["assessment_internal"])
    item = find_item(assessment, item_id)
    if item is None:
        raise ItemNotFound("Interview question not found.")

    score: int | None = None
    completed = False

    if item.type == ItemType.external_practice:
        value = answer.get("completed")
        if not isinstance(value, bool):
            raise InvalidAnswer("completed must be a boolean.")
        completed = value
        feedback: dict[str, Any] = {"completed": value}
    elif item.type == ItemType.multiple_choice:
        score, feedback = _grade_multiple_choice(item, answer)
        completed = True
    else:
        text = answer.get("text")
        if not isinstance(text, str) or not text.strip():
            raise InvalidAnswer("text must be a non-empty string.")
        if len(text) > MAX_RESPONSE_TEXT:
            raise InvalidAnswer(
                f"text must be shorter than or equal to {MAX_RESPONSE_TEXT} characters."
            )
        job = interview_store.load_job(conn, int(attempt["job_id"]))
        score, feedback = _evaluate_written(item, text.strip(), job)
        completed = True

    # Close the read transaction before grading so the model call never holds
    # one open, and so the write below is a real transaction, not a savepoint.
    conn.commit()

    with conn.transaction():
        interview_store.upsert_response(
            conn,
            attempt_id=attempt_id,
            item_id=item_id,
            answer=answer,
            score=score,
            feedback=feedback,
            completed=completed,
        )
        responses = interview_store.list_responses(conn, attempt_id)
        progress = compute_progress(assessment, responses)
        interview_store.update_attempt_progress(
            conn,
            attempt_id=attempt_id,
            progress=progress,
            completed=progress["percent"] == 100,
        )

    return {
        "itemId": item_id,
        "score": score,
        "feedback": feedback,
        "completed": completed,
        "progress": progress,
    }
