import json
import logging
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from services.ranking import FINAL_LIMIT, rank_candidates

logger = logging.getLogger(__name__)

TOP_N = 100
MAX_CV_TEXT = 8_000

PROFILES = """
SELECT user_id, headline, current_title, years_experience, location, summary, cv_data
FROM candidate_profiles
WHERE profile_embedding IS NOT NULL
  AND (%s::uuid IS NULL OR user_id = %s)
ORDER BY user_id
"""

CANDIDATES = """
SELECT j.id, j.title, j.description, j.locations_json, j.employment_type,
       j.workplace_type, j.seniority, j.occupation, j.technologies_json,
       c.name AS company_name, j.distance, 1 - j.distance AS similarity
FROM candidate_profiles p
CROSS JOIN LATERAL (
  SELECT jobs.id, jobs.title, jobs.description, jobs.locations_json,
         jobs.employment_type, jobs.workplace_type, jobs.seniority,
         jobs.occupation, jobs.technologies_json, jobs.company_slug,
         jobs.embedding <=> p.profile_embedding AS distance
  FROM jobs
  WHERE jobs.status = 'open' AND jobs.embedding IS NOT NULL
  ORDER BY jobs.embedding <=> p.profile_embedding
  LIMIT %s
) j
LEFT JOIN companies c ON c.slug = j.company_slug
WHERE p.user_id = %s
ORDER BY j.distance
"""

READ = """
SELECT r.job_id, r.rank, r.score, r.similarity, r.reason,
       j.title, j.url, j.locations_json, j.employment_type,
       j.workplace_type, j.seniority, j.occupation,
       c.name AS company_name
FROM job_recommendations r
JOIN jobs j ON j.id = r.job_id
LEFT JOIN companies c ON c.slug = j.company_slug
WHERE r.user_id = %s
ORDER BY r.rank
"""


def _json_array(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _build_profile_text(profile: dict[str, Any]) -> str:
    parts: list[str] = []

    def add(label: str, value: str | None) -> None:
        text = (value or "").strip()
        if text:
            parts.append(f"{label}: {text}")

    add("Headline", profile["headline"])
    add("Current title", profile["current_title"])
    if profile["years_experience"] is not None:
        parts.append(f"Years of experience: {profile['years_experience']}")
    add("Location", profile["location"])
    add("Summary", profile["summary"])

    cv_text = (profile["cv_data"] or "").strip()
    if cv_text:
        parts.append(f"CV:\n{cv_text[:MAX_CV_TEXT]}")

    return "\n\n".join(parts)


def _to_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": row["title"] or "",
        "company": row["company_name"] or "",
        "locations": _json_array(row["locations_json"]),
        "employment_type": row["employment_type"],
        "workplace_type": row["workplace_type"],
        "seniority": row["seniority"],
        "occupation": row["occupation"],
        "technologies": _json_array(row["technologies_json"]),
        "description": row["description"] or "",
        "similarity": float(row["similarity"] or 0.0),
    }


def _fallback(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "job": candidate,
        "score": round(max(0.0, candidate["similarity"]) * 100, 2),
        "reason": "Matches your profile based on semantic similarity.",
    }


def _fill(ranked: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chosen = {item["job"]["id"] for item in ranked}
    for candidate in candidates:
        if len(ranked) >= FINAL_LIMIT:
            break
        if candidate["id"] not in chosen:
            ranked.append(_fallback(candidate))
    return ranked


def _candidates(conn: psycopg.Connection, user_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(CANDIDATES, (TOP_N, user_id))
        return [_to_candidate(row) for row in cur.fetchall()]


def _save(
    conn: psycopg.Connection, user_id: UUID, ranked: list[dict[str, Any]]
) -> int:
    rows = [
        (
            user_id,
            item["job"]["id"],
            rank,
            item["score"],
            item["job"]["similarity"],
            item["reason"],
        )
        for rank, item in enumerate(ranked, start=1)
    ]

    with conn.transaction():
        conn.execute("DELETE FROM job_recommendations WHERE user_id = %s", (user_id,))
        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO job_recommendations
                      (user_id, job_id, rank, score, similarity, reason)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )

    return len(rows)


def refresh_recommendations(
    conn: psycopg.Connection,
    user_id: UUID | None = None,
) -> int:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(PROFILES, (user_id, user_id))
        profiles = cur.fetchall()

    total = 0
    for profile in profiles:
        owner = profile["user_id"]
        candidates = _candidates(conn, owner)
        if not candidates:
            _save(conn, owner, [])
            continue

        ranked = rank_candidates(_build_profile_text(profile), candidates)
        if ranked is None:
            logger.warning("Falling back to similarity for user %s", owner)
            ranked = [_fallback(candidate) for candidate in candidates[:FINAL_LIMIT]]
        else:
            ranked = _fill(ranked, candidates)

        total += _save(conn, owner, ranked)

    return total


def list_for_user(conn: psycopg.Connection, user_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(READ, (user_id,))
        rows = cur.fetchall()

    return [
        {
            "jobId": int(row["job_id"]),
            "rank": row["rank"],
            "score": row["score"],
            "similarity": row["similarity"],
            "reason": row["reason"],
            "title": row["title"],
            "url": row["url"],
            "locations": _json_array(row["locations_json"]),
            "employmentType": row["employment_type"],
            "workplaceType": row["workplace_type"],
            "seniority": row["seniority"],
            "occupation": row["occupation"],
            "company": row["company_name"],
        }
        for row in rows
    ]
