"""Queue new agent applications."""

from __future__ import annotations

from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from schemas.agent_applications import AgentApplicationStatus

from .platforms import apply_url, detect


class JobsNotFound(RuntimeError):
    def __init__(self, job_ids: list[int]) -> None:
        self.job_ids = job_ids
        joined = ", ".join(str(job_id) for job_id in job_ids)
        super().__init__(f"Jobs not found or closed: {joined}")


def enqueue(
    conn: psycopg.Connection,
    *,
    user_id: UUID,
    job_ids: list[int],
) -> tuple[UUID, list[dict[str, object]], list[int]]:
    unique_ids = list(dict.fromkeys(job_ids))
    batch_id = uuid4()

    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, url, monitor_type
                FROM jobs
                WHERE id = ANY(%s) AND status = 'open'
                """,
                (unique_ids,),
            )
            found = {
                int(row["id"]): row
                for row in cur.fetchall()
            }

        missing = [job_id for job_id in unique_ids if job_id not in found]
        if missing:
            raise JobsNotFound(missing)

        # A job can already be applied to by the agent or manually. In both
        # cases this must not create a second record.
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT job_id FROM agent_applications
                WHERE user_id = %s AND job_id = ANY(%s)
                UNION
                SELECT job_id FROM applications
                WHERE user_id = %s AND job_id = ANY(%s)
                """,
                (user_id, unique_ids, user_id, unique_ids),
            )
            skipped = {int(row["job_id"]) for row in cur.fetchall()}

        to_queue = [
            job_id for job_id in unique_ids if job_id not in skipped
        ]

        rows = []
        for job_id in to_queue:
            job = found[job_id]
            platform = detect(job["monitor_type"], job["url"])
            rows.append(
                (
                    batch_id,
                    user_id,
                    job_id,
                    AgentApplicationStatus.queued.value,
                    platform,
                    apply_url(platform, job["url"]),
                )
            )

        if rows:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO agent_applications
                      (batch_id, user_id, job_id, status, platform, apply_url)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    rows,
                )

    return (
        batch_id,
        [
            {"jobId": job_id, "status": AgentApplicationStatus.queued.value}
            for job_id in to_queue
        ],
        sorted(skipped),
    )
