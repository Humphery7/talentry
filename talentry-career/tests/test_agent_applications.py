from contextlib import nullcontext
from uuid import uuid4

import pytest
from pydantic import ValidationError

from schemas.agent_applications import StartRequest
from services.agent_applications import JobsNotFound, enqueue


class FakeCursor:
    def __init__(self, conn, row_factory=None):
        self.conn = conn
        self.row_factory = row_factory
        self.rows: list[dict[str, int]] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if "FROM jobs" in sql:
            wanted = set(params[0])
            self.rows = [
                {
                    "id": job_id,
                    "url": f"https://example.com/jobs/{job_id}",
                    "monitor_type": "greenhouse",
                }
                for job_id in self.conn.open_job_ids
                if job_id in wanted
            ]
        elif "UNION" in sql:
            wanted = set(params[1])
            self.rows = [
                {"job_id": job_id}
                for job_id in self.conn.applied_job_ids
                if job_id in wanted
            ]

    def fetchall(self):
        return self.rows

    def executemany(self, sql, rows):
        self.conn.inserted.extend(rows)


class FakeConn:
    def __init__(self, open_job_ids, applied_job_ids=()):
        self.open_job_ids = set(open_job_ids)
        self.applied_job_ids = set(applied_job_ids)
        self.inserted: list[tuple] = []

    def cursor(self, row_factory=None):
        return FakeCursor(self, row_factory)

    def transaction(self):
        return nullcontext()


def test_enqueue_dedupes_and_queues_open_jobs() -> None:
    user_id = uuid4()
    conn = FakeConn({7, 9})

    batch_id, jobs, skipped = enqueue(conn, user_id=user_id, job_ids=[9, 7, 9])

    assert [job["jobId"] for job in jobs] == [9, 7]
    assert skipped == []
    assert all(job["status"] == "queued" for job in jobs)
    assert len(conn.inserted) == 2
    assert {row[0] for row in conn.inserted} == {batch_id}
    assert {row[1] for row in conn.inserted} == {user_id}
    assert {row[2] for row in conn.inserted} == {7, 9}
    assert {row[3] for row in conn.inserted} == {"queued"}
    assert {row[4] for row in conn.inserted} == {"greenhouse"}
    assert {row[5] for row in conn.inserted} == {
        "https://example.com/jobs/7",
        "https://example.com/jobs/9",
    }


def test_enqueue_rejects_missing_or_closed_jobs() -> None:
    conn = FakeConn({7})

    with pytest.raises(JobsNotFound) as exc:
        enqueue(conn, user_id=uuid4(), job_ids=[7, 8])

    assert exc.value.job_ids == [8]
    assert conn.inserted == []


def test_enqueue_skips_jobs_that_already_have_an_application() -> None:
    conn = FakeConn({7, 9}, applied_job_ids={9})

    _, jobs, skipped = enqueue(conn, user_id=uuid4(), job_ids=[7, 9])

    assert [job["jobId"] for job in jobs] == [7]
    assert skipped == [9]
    assert [row[2] for row in conn.inserted] == [7]


def test_start_request_requires_valid_job_ids() -> None:
    user_id = uuid4()

    with pytest.raises(ValidationError):
        StartRequest(user_id=user_id, job_ids=[])

    with pytest.raises(ValidationError):
        StartRequest(user_id=user_id, job_ids=[0])
