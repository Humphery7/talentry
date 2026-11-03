import json
from collections.abc import Callable
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from talentry_embeddings import build_profile_text, embed_text

PROFILE = """
SELECT headline, current_title, years_experience, location, summary, cv_data
FROM candidate_profiles
WHERE user_id = %s
"""


def refresh_profile_embedding(
    conn: psycopg.Connection,
    user_id: UUID,
    embedder: Callable[[str], list[float]] = embed_text,
) -> bool | None:
    """Embed the stored profile. Returns None when the profile does not exist."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(PROFILE, (user_id,))
        profile = cur.fetchone()

    if profile is None:
        return None

    text = build_profile_text(
        headline=profile["headline"],
        current_title=profile["current_title"],
        years_experience=profile["years_experience"],
        location=profile["location"],
        summary=profile["summary"],
        cv_text=profile["cv_data"],
    )
    embedding = embedder(text) if text else None
    value = json.dumps(embedding, separators=(",", ":")) if embedding else None

    with conn.transaction():
        conn.execute(
            """
            UPDATE candidate_profiles
            SET profile_embedding = %s::vector, embedding_updated_at = now()
            WHERE user_id = %s
            """,
            (value, user_id),
        )

    return embedding is not None
