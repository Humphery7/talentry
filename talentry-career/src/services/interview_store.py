"""All SQL for interview attempts and responses.

The service writes here; the Express backend reads the same tables.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


def load_job(conn: psycopg.Connection, job_id: int) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT j.id, j.title, j.description, j.seniority, j.occupation,
                   j.technologies_json, j.locations_json, j.employment_type,
                   j.workplace_type, j.status, c.name AS company_name
            FROM jobs j
            LEFT JOIN companies c ON c.slug = j.company_slug
            WHERE j.id = %s
            """,
            (job_id,),
        )
        return cur.fetchone()


def load_profile(conn: psycopg.Connection, user_id: UUID) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT headline, current_title, years_experience, location, summary, cv_data
            FROM candidate_profiles
            WHERE user_id = %s
            """,
            (user_id,),
        )
        return cur.fetchone()


def latest_attempt(
    conn: psycopg.Connection, user_id: UUID, job_id: int
) -> dict[str, Any] | None:
    """The active attempt if there is one, otherwise the most recent attempt."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id
            FROM interview_attempts
            WHERE user_id = %s AND job_id = %s
            ORDER BY (status = 'active') DESC, attempt_no DESC
            LIMIT 1
            """,
            (user_id, job_id),
        )
        return cur.fetchone()


def next_attempt_no(conn: psycopg.Connection, user_id: UUID, job_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(MAX(attempt_no), 0) + 1
            FROM interview_attempts
            WHERE user_id = %s AND job_id = %s
            """,
            (user_id, job_id),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 1


def supersede_active(conn: psycopg.Connection, user_id: UUID, job_id: int) -> None:
    conn.execute(
        """
        UPDATE interview_attempts
        SET status = 'superseded', updated_at = now()
        WHERE user_id = %s AND job_id = %s AND status = 'active'
        """,
        (user_id, job_id),
    )


def insert_attempt(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    job_id: int,
    attempt_no: int,
    title: str,
    role_family: str,
    assessment_internal: dict[str, Any],
    assessment_public: dict[str, Any],
    progress: dict[str, Any],
) -> UUID:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO interview_attempts (
                user_id, job_id, attempt_no, status, title, role_family,
                assessment_internal, assessment_public, progress
            ) VALUES (%s, %s, %s, 'active', %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
            RETURNING id
            """,
            (
                user_id,
                job_id,
                attempt_no,
                title,
                role_family,
                json.dumps(assessment_internal),
                json.dumps(assessment_public),
                json.dumps(progress),
            ),
        )
        return cur.fetchone()["id"]


def get_attempt(
    conn: psycopg.Connection, attempt_id: UUID, user_id: UUID
) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT *
            FROM interview_attempts
            WHERE id = %s AND user_id = %s
            """,
            (attempt_id, user_id),
        )
        return cur.fetchone()


def list_responses(
    conn: psycopg.Connection, attempt_id: UUID
) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT item_id, answer, score, feedback, completed
            FROM interview_responses
            WHERE attempt_id = %s
            """,
            (attempt_id,),
        )
        return list(cur.fetchall())


def upsert_response(
    conn: psycopg.Connection,
    *,
    attempt_id: UUID,
    item_id: str,
    answer: dict[str, Any],
    score: int | None,
    feedback: dict[str, Any],
    completed: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO interview_responses (
            attempt_id, item_id, answer, score, feedback, completed
        ) VALUES (%s, %s, %s::jsonb, %s, %s::jsonb, %s)
        ON CONFLICT (attempt_id, item_id) DO UPDATE SET
            answer = EXCLUDED.answer,
            score = EXCLUDED.score,
            feedback = EXCLUDED.feedback,
            completed = EXCLUDED.completed,
            updated_at = now()
        """,
        (
            attempt_id,
            item_id,
            json.dumps(answer),
            score,
            json.dumps(feedback),
            completed,
        ),
    )


def update_attempt_progress(
    conn: psycopg.Connection,
    *,
    attempt_id: UUID,
    progress: dict[str, Any],
    completed: bool,
) -> None:
    conn.execute(
        """
        UPDATE interview_attempts
        SET progress = %s::jsonb,
            status = CASE
                WHEN status = 'superseded' THEN status
                WHEN %s THEN 'completed'
                ELSE 'active'
            END,
            completed_at = CASE WHEN %s THEN COALESCE(completed_at, now()) ELSE NULL END,
            updated_at = now()
        WHERE id = %s
        """,
        (json.dumps(progress), completed, completed, attempt_id),
    )
