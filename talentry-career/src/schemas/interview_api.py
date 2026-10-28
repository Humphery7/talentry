"""Request/response models for the interview routes."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    user_id: UUID
    job_id: int = Field(ge=1)
    new_attempt: bool = False


class GenerateResult(BaseModel):
    attempt_id: UUID
    created: bool


class AnswerRequest(BaseModel):
    user_id: UUID
    attempt_id: UUID
    item_id: str = Field(min_length=1, max_length=40)
    answer: dict[str, Any]


class AnswerResult(BaseModel):
    itemId: str
    score: int | None
    feedback: dict[str, Any]
    completed: bool
    progress: dict[str, Any]
