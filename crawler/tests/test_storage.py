import sqlite3

import pytest

from talentry_crawler.models import Company, Job
from talentry_crawler.storage import JobStore


@pytest.fixture
def store(tmp_path):
    s = JobStore(tmp_path / "jobs.db")
    yield s
    s.close()


def job(n: int, **extra) -> Job:
    return Job(url=f"https://acme.test/jobs/{n}", title=f"Job {n}", **extra)


def count(store: JobStore, status: str) -> int:
    return store._conn.execute("SELECT COUNT(*) FROM jobs WHERE status = ?", (status,)).fetchone()[0]


def test_first_save_inserts(store, board):
    assert store.save_board_jobs(board, [job(1), job(2)]) == (2, 0, 0)


def test_second_save_updates_and_keeps_first_seen(store, board):
    store.save_board_jobs(board, [job(1)])
    first = store._conn.execute("SELECT first_seen_at FROM jobs").fetchone()[0]

    assert store.save_board_jobs(board, [job(1)]) == (0, 1, 0)

    row = store._conn.execute("SELECT first_seen_at, last_seen_at FROM jobs").fetchone()
    assert row["first_seen_at"] == first
    assert row["last_seen_at"] > first


def test_job_missing_from_next_crawl_is_closed(store, board):
    store.save_board_jobs(board, [job(1), job(2)])
    assert store.save_board_jobs(board, [job(1)]) == (0, 1, 1)
    assert (count(store, "open"), count(store, "closed")) == (1, 1)


def test_closed_job_that_comes_back_is_reopened(store, board):
    store.save_board_jobs(board, [job(1)])
    store.save_board_jobs(board, [])
    assert count(store, "closed") == 1
    store.save_board_jobs(board, [job(1)])
    assert (count(store, "open"), count(store, "closed")) == (1, 0)


def test_closing_only_touches_the_same_board(store, board):
    other = type(board)("beta", "beta-lever", "https://jobs.lever.co/beta", "lever")
    store.save_board_jobs(board, [job(1)])
    store.save_board_jobs(other, [job(2)])
    store.save_board_jobs(board, [])
    assert count(store, "open") == 1  # beta's job is untouched


def test_labels_round_trip(store, board):
    store.save_board_jobs(
        board, [job(1, seniority="senior", occupation="backend-developer", technologies=["python"])]
    )
    row = store._conn.execute("SELECT seniority, occupation, technologies_json FROM jobs").fetchone()
    assert (row["seniority"], row["occupation"], row["technologies_json"]) == (
        "senior",
        "backend-developer",
        '["python"]',
    )


def test_companies_and_sample_join(store, board):
    store.save_companies([Company(slug="acme", name="Acme Inc", industry="Technology")])
    store.save_board_jobs(board, [job(1)])
    assert store.sample(1)[0]["company"] == "Acme Inc"
    assert store.stats()["open_jobs"] == 1


def test_old_database_is_refused_with_a_clear_message(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE jobs (url TEXT PRIMARY KEY, title TEXT)")
    old.commit()
    old.close()
    with pytest.raises(RuntimeError, match="older version"):
        JobStore(path)


def test_embedding_is_kept_when_the_job_is_refreshed_without_one(store, board):
    vector = [0.1, 0.2, 0.3]
    store.save_board_jobs(
        board,
        [job(1, embedding=vector, embedding_text_hash="same")],
    )
    store.save_board_jobs(board, [job(1, embedding_text_hash="same")])

    row = store._conn.execute("SELECT embedding_json FROM jobs").fetchone()
    assert row["embedding_json"] == "[0.1,0.2,0.3]"
