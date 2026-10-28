"""Internal interview prep endpoints called by the Express backend.

There is no user auth here on purpose. The backend verifies the JWT and sends
the trusted `user_id`; this service should only be reachable from the backend.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from db.connect import ConnectionDep
from schemas.interview_api import (
    AnswerRequest,
    AnswerResult,
    GenerateRequest,
    GenerateResult,
)
from services.interview_evaluation import (
    AttemptNotFound,
    InvalidAnswer,
    ItemNotFound,
    evaluate_answer,
)
from services.interview_generation import (
    GenerationError,
    JobNotFound,
    generate_assessment,
)

router = APIRouter(prefix="/interview", tags=["interview"])


@router.post("/generate", response_model=GenerateResult)
def generate(body: GenerateRequest, conn: ConnectionDep) -> GenerateResult:
    try:
        attempt_id, created = generate_assessment(
            conn,
            user_id=body.user_id,
            job_id=body.job_id,
            new_attempt=body.new_attempt,
        )
    except JobNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return GenerateResult(attempt_id=attempt_id, created=created)


@router.post("/evaluate", response_model=AnswerResult)
def evaluate(body: AnswerRequest, conn: ConnectionDep) -> AnswerResult:
    try:
        result = evaluate_answer(
            conn,
            user_id=body.user_id,
            attempt_id=body.attempt_id,
            item_id=body.item_id,
            answer=body.answer,
        )
    except AttemptNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ItemNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidAnswer as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return AnswerResult(**result)
