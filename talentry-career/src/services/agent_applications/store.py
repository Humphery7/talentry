"""SQL used by the agent application worker."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from schemas.agent_applications import AgentApplicationStatus

from .facts import normalize

ACTIVE_STATUSES = (
    AgentApplicationStatus.in_progress.value,
    AgentApplicationStatus.submitting.value,
)


class Cancelled(RuntimeError):
    """The user changed the application while the worker was running."""


class NotFound(RuntimeError):
    """The application does not exist for this user."""


class InvalidState(RuntimeError):
    """The application is not in a state that allows this action."""


def recover_stale(conn: psycopg.Connection, minutes: int) -> None:
    conn.execute(
        """
        UPDATE agent_applications
        SET status = 'queued', updated_at = now()
        WHERE status = 'in_progress'
          AND heartbeat_at < now() - make_interval(mins => %s)
        """,
        (minutes,),
    )
    conn.execute(
        """
        UPDATE agent_applications
        SET status = 'unconfirmed',
            error = 'The worker stopped while submitting. Check the employer site before retrying.',
            completed_at = now(),
            updated_at = now()
        WHERE status = 'submitting'
          AND heartbeat_at < now() - make_interval(mins => %s)
        """,
        (minutes,),
    )


def claim_next(conn: psycopg.Connection) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            WITH next AS (
              SELECT id
              FROM agent_applications
              WHERE status IN ('queued', 'approved')
                AND (run_after IS NULL OR run_after <= now())
              ORDER BY updated_at
              LIMIT 1
              FOR UPDATE SKIP LOCKED
            )
            UPDATE agent_applications a
            SET status = CASE a.status
                  WHEN 'approved' THEN 'submitting'
                  ELSE 'in_progress'
                END,
                started_at = COALESCE(a.started_at, now()),
                heartbeat_at = now(),
                updated_at = now(),
                error = NULL
            FROM next
            WHERE a.id = next.id
            RETURNING a.*
            """
        )
        return cur.fetchone()


def load_context(
    conn: psycopg.Connection,
    application: dict[str, Any],
) -> dict[str, Any]:
    user_id = application["user_id"]
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, name, email FROM users WHERE id = %s",
            (user_id,),
        )
        user = cur.fetchone()

        cur.execute(
            "SELECT * FROM candidate_profiles WHERE user_id = %s",
            (user_id,),
        )
        profile = cur.fetchone()

        cur.execute(
            """
            SELECT j.id, j.url, j.title, j.description, j.monitor_type,
                   c.name AS company
            FROM jobs j
            LEFT JOIN companies c ON c.slug = j.company_slug
            WHERE j.id = %s
            """,
            (application["job_id"],),
        )
        job = cur.fetchone()

        cur.execute(
            """
            SELECT question_key, question, answer
            FROM applicant_answers
            WHERE user_id = %s
            """,
            (user_id,),
        )
        bank = {
            row["question_key"]: row
            for row in cur.fetchall()
        }

    return {
        "user": user or {},
        "profile": profile,
        "job": job or {},
        "bank": bank,
    }


def checkpoint(
    conn: psycopg.Connection,
    application_id: str | UUID,
    plan: dict[str, Any],
    attention: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    cur = conn.execute(
        """
        UPDATE agent_applications
        SET plan = %s,
            attention = %s,
            warnings = %s,
            heartbeat_at = now(),
            updated_at = now()
        WHERE id = %s AND status = ANY(%s)
        """,
        (
            Jsonb(plan),
            Jsonb(attention),
            Jsonb(warnings),
            application_id,
            list(ACTIVE_STATUSES),
        ),
    )
    if cur.rowcount == 0:
        raise Cancelled()


def refresh_attention(
    conn: psycopg.Connection,
    application_id: str | UUID,
) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT attention FROM agent_applications WHERE id = %s",
            (application_id,),
        )
        row = cur.fetchone()
    return list((row or {}).get("attention") or [])


def finish(
    conn: psycopg.Connection,
    application_id: str | UUID,
    status: str,
    **columns: Any,
) -> None:
    assignments = ["status = %s", "updated_at = now()"]
    if status in {"submitted", "unconfirmed", "failed", "cancelled"}:
        assignments.append("completed_at = now()")
    values: list[Any] = [status]
    for key, value in columns.items():
        assignments.append(f"{key} = %s")
        values.append(Jsonb(value) if isinstance(value, (dict, list)) else value)
    values.extend([application_id, list(ACTIVE_STATUSES)])
    cur = conn.execute(
        f"""
        UPDATE agent_applications
        SET {", ".join(assignments)}
        WHERE id = %s AND status = ANY(%s)
        """,
        values,
    )
    if cur.rowcount == 0:
        raise Cancelled()


def requeue(
    conn: psycopg.Connection,
    application_id: str | UUID,
    status: str,
    delay_seconds: int,
    error: str,
) -> None:
    conn.execute(
        """
        UPDATE agent_applications
        SET status = %s,
            error = %s,
            attempts = attempts + 1,
            completed_at = NULL,
            updated_at = now(),
            run_after = now() + make_interval(secs => %s)
        WHERE id = %s
        """,
        (status, error, delay_seconds, application_id),
    )


def event(
    conn: psycopg.Connection,
    application_id: str | UUID,
    kind: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO agent_application_events
          (agent_application_id, kind, message, data)
        VALUES (%s, %s, %s, %s)
        """,
        (
            application_id,
            kind,
            message,
            Jsonb(data) if data is not None else None,
        ),
    )


def docs(
    conn: psycopg.Connection,
    application_id: str | UUID,
) -> dict[str, dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (kind) *
            FROM agent_application_documents
            WHERE agent_application_id = %s
            ORDER BY kind, version DESC
            """,
            (application_id,),
        )
        return {row["kind"]: row for row in cur.fetchall()}


def doc_version(
    conn: psycopg.Connection,
    application_id: str | UUID,
    kind: str,
    version: int,
) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT *
            FROM agent_application_documents
            WHERE agent_application_id = %s AND kind = %s AND version = %s
            """,
            (application_id, kind, version),
        )
        return cur.fetchone()


def add_doc(
    conn: psycopg.Connection,
    application_id: str | UUID,
    kind: str,
    content: str,
    origin: str,
    notes: list[str],
) -> int:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO agent_application_documents
              (agent_application_id, kind, version, content, origin, notes)
            VALUES (
              %s,
              %s,
              (
                SELECT COALESCE(MAX(version), 0) + 1
                FROM agent_application_documents
                WHERE agent_application_id = %s AND kind = %s
              ),
              %s,
              %s,
              %s
            )
            RETURNING version
            """,
            (
                application_id,
                kind,
                application_id,
                kind,
                content,
                origin,
                Jsonb(notes),
            ),
        )
        row = cur.fetchone()
    return int(row["version"])


def set_options(
    conn: psycopg.Connection,
    application_id: str | UUID,
    options: dict[str, Any],
) -> None:
    conn.execute(
        """
        UPDATE agent_applications
        SET options = %s, updated_at = now()
        WHERE id = %s
        """,
        (Jsonb(options), application_id),
    )


def get_application(
    conn: psycopg.Connection,
    application_id: str | UUID,
) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM agent_applications WHERE id = %s",
            (application_id,),
        )
        return cur.fetchone()


def notify(
    conn: psycopg.Connection,
    application: dict[str, Any],
    kind: str,
    title: str,
    body: str = "",
) -> None:
    conn.execute(
        """
        INSERT INTO notifications
          (user_id, agent_application_id, kind, title, body)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            application["user_id"],
            application["id"],
            kind,
            title,
            body,
        ),
    )


def list_for_user(
    conn: psycopg.Connection,
    user_id: UUID | str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT a.*, j.title AS job_title, c.name AS company
            FROM agent_applications a
            JOIN jobs j ON j.id = a.job_id
            LEFT JOIN companies c ON c.slug = j.company_slug
            WHERE a.user_id = %s
            ORDER BY a.created_at DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return list(cur.fetchall())


def detail_for_user(
    conn: psycopg.Connection,
    application_id: UUID | str,
    user_id: UUID | str,
) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT a.*, j.title AS job_title, c.name AS company
            FROM agent_applications a
            JOIN jobs j ON j.id = a.job_id
            LEFT JOIN companies c ON c.slug = j.company_slug
            WHERE a.id = %s AND a.user_id = %s
            """,
            (application_id, user_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cur.execute(
            """
            SELECT kind, version, origin, notes, content
            FROM agent_application_documents
            WHERE agent_application_id = %s
            ORDER BY kind, version DESC
            """,
            (application_id,),
        )
        row["documents"] = cur.fetchall()
    return row


def answer(
    conn: psycopg.Connection,
    application_id: UUID | str,
    user_id: UUID | str,
    answers: dict[str, str],
) -> int:
    row = get_for_user(conn, application_id, user_id)
    if row is None:
        raise NotFound()
    if row["status"] != AgentApplicationStatus.needs_input.value:
        raise InvalidState("This application is not waiting for answers.")

    attention = list(row.get("attention") or [])
    by_id = {
        item["id"]: item
        for item in attention
        if item.get("id")
    }
    answered = 0
    for attention_id, value in answers.items():
        item = by_id.get(attention_id)
        text = value.strip()
        if (
            item is None
            or item.get("kind") != "question"
            or item.get("answer") is not None
            or not text
        ):
            continue
        item["answer"] = text
        answered += 1
        question_key = (
            f"fact:{item['fact_key']}"
            if item.get("fact_key")
            else item.get("field_key")
            or normalize(item.get("question"))
        )
        conn.execute(
            """
            INSERT INTO applicant_answers
              (user_id, question_key, question, answer)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, question_key) DO UPDATE
            SET question = EXCLUDED.question,
                answer = EXCLUDED.answer,
                updated_at = now()
            """,
            (
                user_id,
                question_key,
                item.get("question") or question_key,
                text,
            ),
        )

    if answered == 0:
        raise InvalidState("No unanswered items matched.")

    conn.execute(
        """
        UPDATE agent_applications
        SET status = 'queued',
            attention = %s,
            error = NULL,
            run_after = now(),
            updated_at = now()
        WHERE id = %s AND user_id = %s
        """,
        (Jsonb(attention), application_id, user_id),
    )
    event(
        conn,
        application_id,
        "answers",
        f"Saved {answered} answer(s).",
    )
    return answered


def get_for_user(
    conn: psycopg.Connection,
    application_id: UUID | str,
    user_id: UUID | str,
) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT *
            FROM agent_applications
            WHERE id = %s AND user_id = %s
            """,
            (application_id, user_id),
        )
        return cur.fetchone()


def open_questions(attention: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Questions the candidate still has to answer.

    Manual notes (a CAPTCHA, a form that changed) are information, not
    questions. They must never block approval.
    """
    return [
        item
        for item in attention
        if item.get("kind") == "question" and item.get("answer") is None
    ]


def approve(
    conn: psycopg.Connection,
    application_id: UUID | str,
    user_id: UUID | str,
) -> dict[str, Any]:
    row = get_for_user(conn, application_id, user_id)
    if row is None:
        raise NotFound()
    if row["status"] != AgentApplicationStatus.pending_approval.value:
        raise InvalidState("This application is not ready for approval.")

    # Manual notes are cleared on approval; real questions are not.
    attention = [
        item
        for item in (row.get("attention") or [])
        if item.get("kind") != "manual"
    ]
    pending_questions = open_questions(attention)
    if pending_questions:
        listed = "; ".join(
            f"“{item.get('question')}”" for item in pending_questions[:3]
        )
        raise InvalidState(f"Answer these questions before approving: {listed}")

    plan = row.get("plan") or {}
    fields = plan.get("fields") or {}
    snapshot = {
        "fields": {
            key: {
                "value": value.get("value"),
                "doc": value.get("doc"),
            }
            for key, value in fields.items()
        },
        "documents": {
            kind: int(doc["version"])
            for kind, doc in docs(conn, application_id).items()
        },
    }
    cur = conn.execute(
        """
        UPDATE agent_applications
        SET status = 'approved',
            attention = %s,
            approved_snapshot = %s,
            approved_at = now(),
            error = NULL,
            run_after = now(),
            heartbeat_at = NULL,
            updated_at = now()
        WHERE id = %s AND user_id = %s AND status = 'pending_approval'
        """,
        (Jsonb(attention), Jsonb(snapshot), application_id, user_id),
    )
    if cur.rowcount == 0:
        raise InvalidState("The application changed while approving.")
    event(
        conn,
        application_id,
        "approved",
        "The candidate approved this application.",
    )
    return snapshot


def retry(
    conn: psycopg.Connection,
    application_id: UUID | str,
    user_id: UUID | str,
) -> None:
    row = get_for_user(conn, application_id, user_id)
    if row is None:
        raise NotFound()
    allowed = {
        AgentApplicationStatus.failed.value,
        AgentApplicationStatus.unconfirmed.value,
        AgentApplicationStatus.pending_approval.value,
        AgentApplicationStatus.needs_input.value,
        AgentApplicationStatus.cancelled.value,
    }
    if row["status"] not in allowed:
        raise InvalidState("This application cannot be retried.")
    conn.execute(
        """
        UPDATE agent_applications
        SET status = 'queued',
            approved_snapshot = NULL,
            approved_at = NULL,
            error = NULL,
            result = NULL,
            submitted_at = NULL,
            attempts = 0,
            run_after = now(),
            heartbeat_at = NULL,
            completed_at = NULL,
            updated_at = now()
        WHERE id = %s AND user_id = %s
        """,
        (application_id, user_id),
    )
    event(conn, application_id, "retry", "The candidate retried.")


def cancel(
    conn: psycopg.Connection,
    application_id: UUID | str,
    user_id: UUID | str,
) -> None:
    row = get_for_user(conn, application_id, user_id)
    if row is None:
        raise NotFound()
    if row["status"] in {
        AgentApplicationStatus.submitted.value,
        AgentApplicationStatus.submitting.value,
    }:
        raise InvalidState("This application can no longer be cancelled.")
    conn.execute(
        """
        UPDATE agent_applications
        SET status = 'cancelled',
            completed_at = now(),
            updated_at = now()
        WHERE id = %s AND user_id = %s
        """,
        (application_id, user_id),
    )
    event(conn, application_id, "cancelled", "The candidate cancelled.")
