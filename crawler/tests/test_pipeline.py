"""One board, end to end: fake API -> adapter -> labeler -> database."""

import httpx
import pytest

from talentry_crawler.config import load_label_dictionaries
from talentry_crawler.labeling import Labeler
from talentry_crawler.pipeline import crawl_boards, crawl_one_board
from talentry_crawler.storage import JobStore


def greenhouse_job(n: int, title: str) -> dict:
    return {
        "absolute_url": f"https://boards.greenhouse.io/acme/jobs/{n}",
        "title": title,
        "content": "&lt;p&gt;We use Python and AWS.&lt;/p&gt;",
    }


@pytest.fixture
def store(tmp_path):
    s = JobStore(tmp_path / "jobs.db")
    yield s
    s.close()


@pytest.fixture(scope="module")
def labeler():
    return Labeler(load_label_dictionaries())


def fake_embedder(texts):
    return [[0.1] * 384 for _ in texts]


async def crawl(board, store, labeler, response: httpx.Response, embedder=fake_embedder):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response)) as client:
        return await crawl_one_board(
            board, client, labeler, store, embedder=embedder
        )


async def test_jobs_are_fetched_labeled_and_saved(board, store, labeler):
    reply = httpx.Response(200, json={"jobs": [greenhouse_job(1, "Senior Backend Engineer")]})
    result = await crawl(board, store, labeler, reply)

    assert (result.error, result.job_count, result.inserted) == (None, 1, 1)
    row = store._conn.execute("SELECT * FROM jobs").fetchone()
    assert row["seniority"] == "senior"
    assert row["occupation"] == "backend-developer"
    assert row["technologies_json"] == '["python", "aws"]'
    assert row["description"].startswith("<p>")
    assert row["embedding_json"] is not None
    assert row["embedding_text_hash"] is not None


async def test_job_that_disappears_is_closed_on_next_run(board, store, labeler):
    two = httpx.Response(200, json={"jobs": [greenhouse_job(1, "A"), greenhouse_job(2, "B")]})
    one = httpx.Response(200, json={"jobs": [greenhouse_job(1, "A")]})
    await crawl(board, store, labeler, two)
    result = await crawl(board, store, labeler, one)
    assert (result.job_count, result.updated, result.closed) == (1, 1, 1)


async def test_failed_fetch_changes_nothing(board, store, labeler):
    await crawl(board, store, labeler, httpx.Response(200, json={"jobs": [greenhouse_job(1, "A")]}))
    result = await crawl(board, store, labeler, httpx.Response(500))

    assert result.error and "500" in result.error
    assert store.stats()["open_jobs"] == 1  # the site was down; its job is NOT closed


async def test_unknown_ats_name_is_rejected_before_any_work():
    with pytest.raises(ValueError, match="workday"):
        await crawl_boards(ats=["workday"])


async def test_unchanged_jobs_are_not_embedded_again(board, store, labeler):
    calls = []

    def embedder(texts):
        calls.append(len(texts))
        return fake_embedder(texts)

    reply = httpx.Response(200, json={"jobs": [greenhouse_job(1, "Backend Engineer")]})
    await crawl(board, store, labeler, reply, embedder)
    await crawl(board, store, labeler, reply, embedder)

    assert calls == [1]


async def test_changed_job_is_embedded_again(board, store, labeler):
    calls = []

    def embedder(texts):
        calls.append(len(texts))
        return fake_embedder(texts)

    first = httpx.Response(200, json={"jobs": [greenhouse_job(1, "Backend Engineer")]})
    second = httpx.Response(200, json={"jobs": [greenhouse_job(1, "Senior Backend Engineer")]})
    await crawl(board, store, labeler, first, embedder)
    await crawl(board, store, labeler, second, embedder)

    assert calls == [1, 1]
