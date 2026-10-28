"""Request/response models for the recommendation routes."""

from uuid import UUID

from pydantic import BaseModel


class RefreshResult(BaseModel):
    user_id: UUID | None = None
    count: int


class RecommendationItem(BaseModel):
    jobId: int
    rank: int
    score: float
    similarity: float | None = None
    reason: str | None = None
    title: str
    url: str
    locations: list[str]
    employmentType: str | None = None
    workplaceType: str | None = None
    seniority: str | None = None
    occupation: str | None = None
    company: str | None = None
