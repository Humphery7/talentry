from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from db.connect import ConnectionDep
from services.recommendations import list_for_user, refresh_recommendations

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


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


@router.post("/refresh")
def refresh_all(conn: ConnectionDep) -> RefreshResult:
    count = refresh_recommendations(conn)
    return RefreshResult(count=count)


@router.post("/{user_id}")
def refresh_user(user_id: UUID, conn: ConnectionDep) -> RefreshResult:
    count = refresh_recommendations(conn, user_id)
    return RefreshResult(user_id=user_id, count=count)


@router.get("/{user_id}")
def get_user_recommendations(
    user_id: UUID, conn: ConnectionDep
) -> list[RecommendationItem]:
    return [RecommendationItem(**row) for row in list_for_user(conn, user_id)]
