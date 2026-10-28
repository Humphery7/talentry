from uuid import UUID

from fastapi import APIRouter

from db.connect import ConnectionDep
from schemas.recommendations import RecommendationItem, RefreshResult
from services.recommendations import list_for_user, refresh_recommendations

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


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
