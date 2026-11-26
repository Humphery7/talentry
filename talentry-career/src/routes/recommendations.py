from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.connect import ConnectionDep
from schemas.recommendations import RecommendationItem, RefreshResult
from services import ai_keys
from services.recommendations import list_for_user, refresh_recommendations

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


class RefreshRequest(BaseModel):
    """Filters are optional; omitting them keeps whatever is already saved."""

    filters: dict[str, Any] | None = None


@router.post("/refresh")
def refresh_all(conn: ConnectionDep) -> RefreshResult:
    # The all-users sweep skips anyone without a key rather than failing every
    # other user's refresh.
    count = refresh_recommendations(conn)
    return RefreshResult(count=count)


@router.post("/{user_id}")
def refresh_user(
    user_id: UUID,
    conn: ConnectionDep,
    body: RefreshRequest | None = None,
) -> RefreshResult:
    try:
        api_key = ai_keys.require_key(conn, user_id)
        count = refresh_recommendations(
            conn,
            user_id,
            api_key=api_key,
            # `None` = keep saved filters; `{}` = clear them.
            filters=None if body is None else (body.filters or {}),
        )
    except ai_keys.MissingApiKey as exc:
        raise HTTPException(status_code=428, detail=str(exc)) from exc
    return RefreshResult(user_id=user_id, count=count)


@router.get("/{user_id}")
def get_user_recommendations(
    user_id: UUID, conn: ConnectionDep
) -> list[RecommendationItem]:
    return [RecommendationItem(**row) for row in list_for_user(conn, user_id)]
