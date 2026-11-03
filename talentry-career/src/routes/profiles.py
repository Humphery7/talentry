from uuid import UUID

from fastapi import APIRouter, HTTPException

from db.connect import ConnectionDep
from services.profile_embeddings import refresh_profile_embedding

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("/{user_id}/embedding")
def refresh_embedding(user_id: UUID, conn: ConnectionDep) -> dict[str, object]:
    embedded = refresh_profile_embedding(conn, user_id)
    if embedded is None:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return {"user_id": user_id, "embedded": embedded}
