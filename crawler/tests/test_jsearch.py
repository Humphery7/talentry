"""JSearch: the adapter mapping, cross-search dedupe, and the request budget."""

from datetime import datetime, timezone

import httpx
import pytest

from talentry_crawler.ats import jsearch
from talentry_crawler.config import load_label_dictionaries
from talentry_crawler.labeling import Labeler
from talentry_crawler.models import Board, Company, Job
from talentry_crawler.pipeline import crawl_one_board
from talentry_crawler.pipeline.jsearch_budget import (
    plan_jsearch,
    record_jsearch_spend,
)
from talentry_crawler.storage import JobStore

NOW = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)


def jsearch_board(query: str = "software engineer jobs in chicago", **extra) -> Board:
    config = {
        "query": query,
        "country": "us",
        "language": "en",
        "date_posted": "week",
        "num_pages": 1,
        **extra,
    }
    return Board(
        company_slug="jsearch",
        board_slug=f"jsearch-{query.replace(' ', '-')}",
        board_url=jsearch.DEFAULT_API_URL,
        monitor_type="jsearch",
        monitor_config=config,
    )


def raw_job(**overrides):
    job = {
        "job_id": "RHRKX0ZRY1pSUlMzWG5XUEFBQUFBQT09",
        "job_uid": "DtJ_FQcZRRS3XnWPAAAAAA==",
        "job_title": "Software Developer (Backend SaaS)",
        "employer_name": "Canonical",
        "employer_logo": "https://encrypted-tbn0.gstatic.com/logo.png",
        "employer_website": "https://canonical.com",
        "job_publisher": "Jooble",
        "job_employment_type": "Full-time",
        "job_employment_types": ["FULLTIME"],
        "job_apply_link": "https://jooble.org/jdp/1",
        "job_apply_is_direct": False,
        "apply_options": [
            {"apply_link": "https://jooble.org/jdp/1", "is_direct": False, "publisher": "Jooble"}
        ],
        "job_description": "Job Description\n\nBuild things with Python.\nShip them.",
        "job_is_remote": False,
        "job_posted_at": "6 days ago",
        "job_posted_at_timestamp": 1794873600,
        "job_posted_at_datetime_utc": "2026-11-17T00:00:00.000Z",
        "job_location": "Chicago, IL",
        "job_city": "Chicago",
        "job_state": "Illinois",
        "job_country": "US",
        "job_min_salary": 100000,
        "job_max_salary": 140000,
        "job_salary_period": "YEAR",
        "job_google_link": "https://www.google.com/search?q=jobs",
    }
    job.update(overrides)
    return job


def payload(*jobs) -> dict:
    return {
        "status": "OK",
        "request_id": "req-1",
        "parameters": {},
        "data": {"jobs": list(jobs), "cursor": None},
    }


def client_replying(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def api_key(monkeypatch):
    monkeypatch.setenv("JSEARCH_API_KEY", "test-key")
    jsearch.reset_country_pool()


# ---- the adapter ----------------------------------------------------------


async def test_jsearch_maps_every_column_the_crawler_stores():
    board = jsearch_board()

    def reply(request):
        assert request.headers["X-API-Key"] == "test-key"
        assert request.url.params["query"] == "software engineer jobs in chicago"
        assert request.url.params["num_pages"] == "1"
        assert request.url.params["country"] == "us"
        assert request.url.params["date_posted"] == "week"
        return httpx.Response(200, json=payload(raw_job()))

    async with client_replying(reply) as client:
        [job] = await jsearch.discover(board, client)

    assert job.url == "https://jooble.org/jdp/1"
    assert job.title == "Software Developer (Backend SaaS)"
    assert job.description == (
        "<p>Job Description</p>\n<p>Build things with Python.<br>Ship them.</p>"
    )
    assert job.locations == ["Chicago, IL"]
    assert job.employment_type == "Full-time"
    assert job.workplace_type == "OnSite"
    assert job.date_posted == "2026-11-17"
    assert job.salary == {"min": 100000, "max": 140000, "currency": "USD", "unit": "year"}
    assert job.external_id == "DtJ_FQcZRRS3XnWPAAAAAA=="
    assert job.company_slug == "canonical"
    assert job.company_name == "Canonical"
    assert job.company_logo_url == "https://encrypted-tbn0.gstatic.com/logo.png"
    assert job.company_website == "https://canonical.com"
    assert job.metadata == {
        "job_id": "RHRKX0ZRY1pSUlMzWG5XUEFBQUFBQT09",
        "publisher": "Jooble",
        "google_link": "https://www.google.com/search?q=jobs",
        "employment_types": ["FULLTIME"],
        "apply_is_direct": False,
    }


async def test_jsearch_prefers_a_direct_apply_link():
    board = jsearch_board()
    job = raw_job(
        apply_options=[
            {"apply_link": "https://jooble.org/jdp/1", "is_direct": False},
            {"apply_link": "https://canonical.com/careers/1", "is_direct": True},
        ]
    )

    async with client_replying(lambda r: httpx.Response(200, json=payload(job))) as client:
        [parsed] = await jsearch.discover(board, client)

    assert parsed.url == "https://canonical.com/careers/1"


async def test_jsearch_remote_job_has_no_invented_location():
    board = jsearch_board()
    job = raw_job(
        job_is_remote=True,
        job_location=None,
        job_city=None,
        job_state=None,
        job_country=None,
        job_min_salary=None,
        job_max_salary=None,
    )

    async with client_replying(lambda r: httpx.Response(200, json=payload(job))) as client:
        [parsed] = await jsearch.discover(board, client)

    assert parsed.workplace_type == "Remote"
    assert parsed.locations == ["Remote"]
    assert parsed.salary is None


async def test_jsearch_stores_one_job_when_a_page_repeats_it():
    board = jsearch_board()
    repeated = [raw_job(), raw_job(job_apply_link="https://indeed.com/viewjob?jk=1")]

    async with client_replying(lambda r: httpx.Response(200, json=payload(*repeated))) as client:
        jobs = await jsearch.discover(board, client)

    assert len(jobs) == 1


async def test_jsearch_skips_postings_without_a_title_or_link():
    board = jsearch_board()
    jobs = [
        raw_job(job_title=None),
        raw_job(job_apply_link=None, job_google_link=None, apply_options=[]),
    ]

    async with client_replying(lambda r: httpx.Response(200, json=payload(*jobs))) as client:
        assert await jsearch.discover(board, client) == []


async def test_jsearch_reports_a_used_up_quota():
    board = jsearch_board()
    async with client_replying(lambda r: httpx.Response(429)) as client:
        with pytest.raises(RuntimeError, match="quota"):
            await jsearch.discover(board, client)


async def test_jsearch_needs_an_api_key(monkeypatch):
    monkeypatch.delenv("JSEARCH_API_KEY")
    board = jsearch_board()
    async with client_replying(lambda r: httpx.Response(200, json=payload())) as client:
        with pytest.raises(RuntimeError, match="JSEARCH_API_KEY"):
            await jsearch.discover(board, client)


# ---- picking a country per request ---------------------------------------


def test_jsearch_cycles_countries_without_repeating(monkeypatch):
    monkeypatch.setattr(jsearch.random, "sample", lambda codes, k: list(reversed(codes)))

    picks = [jsearch._country({"countries": ["ca", "ng", "de"]}) for _ in range(4)]

    # The whole list is covered before it reshuffles and starts again.
    assert picks == ["de", "ng", "ca", "de"]


def test_jsearch_country_list_wins_over_a_pinned_country(monkeypatch):
    monkeypatch.setattr(jsearch.random, "sample", lambda codes, k: list(codes))

    assert jsearch._country({"countries": ["ca"], "country": "us"}) == "ca"


def test_jsearch_defaults_to_us_without_a_country(monkeypatch):
    assert jsearch._country({}) == "us"
    assert jsearch._country({"countries": []}) == "us"


async def test_jsearch_request_carries_the_sampled_country(monkeypatch):
    board = jsearch_board(countries=["ca", "ng"])
    monkeypatch.setattr(jsearch.random, "sample", lambda codes, k: list(codes))
    seen: list[str] = []

    def reply(request):
        seen.append(request.url.params["country"])
        return httpx.Response(200, json=payload(raw_job()))

    async with client_replying(reply) as client:
        await jsearch.discover(board, client)

    assert seen == ["ca"]


# ---- storage + pipeline ---------------------------------------------------


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


async def crawl(board: Board, store: JobStore, labeler: Labeler, *jobs):
    async with client_replying(
        lambda r: httpx.Response(200, json=payload(*jobs))
    ) as client:
        return await crawl_one_board(board, client, labeler, store, embedder=fake_embedder)


async def test_same_posting_from_two_searches_is_stored_once(store, labeler):
    first = jsearch_board("software engineer jobs in chicago")
    second = jsearch_board("backend developer jobs in chicago")
    job = raw_job(
        job_title="Senior Backend Engineer",
        job_description="Python and AWS.",
    )
    other_url = raw_job(
        job_title="Senior Backend Engineer",
        job_description="Python and AWS.",
        job_apply_link="https://indeed.com/viewjob?jk=1",
        apply_options=[],
    )

    assert (await crawl(first, store, labeler, job)).inserted == 1
    result = await crawl(second, store, labeler, other_url)

    assert (result.inserted, result.updated) == (0, 1)
    rows = store._conn.execute("SELECT url, external_id FROM jobs").fetchall()
    assert len(rows) == 1
    assert rows[0]["url"] == "https://jooble.org/jdp/1"


async def test_a_posting_seen_again_is_refreshed_not_reinserted(store, labeler):
    board = jsearch_board()
    job = raw_job(job_title="Senior Backend Engineer", job_description="Python.")
    await crawl(board, store, labeler, job)
    first = store._conn.execute("SELECT first_seen_at FROM jobs").fetchone()[0]

    result = await crawl(board, store, labeler, job)

    assert (result.inserted, result.updated) == (0, 1)
    row = store._conn.execute("SELECT first_seen_at, last_seen_at FROM jobs").fetchone()
    assert row["first_seen_at"] == first
    assert row["last_seen_at"] > first


async def test_jsearch_never_closes_jobs_missing_from_todays_page(store, labeler):
    board = jsearch_board()
    job = raw_job(job_title="Senior Backend Engineer", job_description="Python.")
    await crawl(board, store, labeler, job)
    result = await crawl(board, store, labeler)  # empty page: not "gone", just page 1 of N

    assert (result.closed, store.stats()["open_jobs"]) == (0, 1)


async def test_employer_arrives_with_the_job_and_is_not_overwritten(store, labeler):
    store.save_companies([Company(slug="canonical", name="Canonical Ltd", industry="Software")])
    job = raw_job(job_title="Senior Backend Engineer", job_description="Python.")

    await crawl(jsearch_board(), store, labeler, job)

    row = store._conn.execute(
        "SELECT name, industry, logo_url FROM companies WHERE slug = 'canonical'"
    ).fetchone()
    assert row["name"] == "Canonical Ltd"  # curated name wins
    assert row["industry"] == "Software"  # curated industry kept
    assert row["logo_url"] == "https://encrypted-tbn0.gstatic.com/logo.png"
    stored = store._conn.execute("SELECT company_slug FROM jobs").fetchone()
    assert stored["company_slug"] == "canonical"


async def test_a_new_employer_is_created_from_the_posting(store, labeler):
    job = raw_job(job_title="Senior Backend Engineer", job_description="Python.")

    await crawl(jsearch_board(), store, labeler, job)

    row = store._conn.execute(
        "SELECT name, website, logo_url FROM companies WHERE slug = 'canonical'"
    ).fetchone()
    assert row["name"] == "Canonical"
    assert row["website"] == "https://canonical.com"


# ---- the request budget ---------------------------------------------------


@pytest.fixture
def budget(monkeypatch):
    monkeypatch.setenv("JSEARCH_API_KEY", "test-key")
    monkeypatch.setenv("JSEARCH_MONTHLY_REQUESTS", "4")
    monkeypatch.setenv("JSEARCH_WEEKLY_REQUESTS", "2")
    monkeypatch.setenv("JSEARCH_MAX_ROWS", "5000")
    monkeypatch.setenv("DB_STORAGE_LIMIT_MB", "1000")


def test_jsearch_runs_once_a_week_even_though_the_crawler_runs_daily(store, budget):
    boards = [jsearch_board(f"software engineer jobs in city {i}") for i in range(4)]

    first = plan_jsearch(store, boards, now=NOW)
    assert len(first.boards) == 2 and first.requests == 2
    record_jsearch_spend(store, first.requests, now=NOW)

    later_same_week = plan_jsearch(store, boards, now=NOW)
    assert later_same_week.boards == []
    assert "already ran this week" in (later_same_week.note or "")

    next_week = plan_jsearch(store, boards, now=datetime(2026, 12, 1, 9, tzinfo=timezone.utc))
    assert len(next_week.boards) == 2


def test_force_runs_again_but_still_obeys_the_month(store, budget):
    boards = [jsearch_board(f"software engineer jobs in city {i}") for i in range(4)]
    first = plan_jsearch(store, boards, now=NOW)
    record_jsearch_spend(store, first.requests, now=NOW)

    forced = plan_jsearch(store, boards, force=True, now=NOW)
    assert len(forced.boards) == 2
    record_jsearch_spend(store, forced.requests, now=NOW)

    spent = plan_jsearch(store, boards, force=True, now=NOW)
    assert spent.boards == []
    assert "monthly request budget spent" in (spent.note or "")


def test_weekly_allowance_rotates_through_the_query_list(store, budget):
    boards = [jsearch_board(f"software engineer jobs in city {i}") for i in range(4)]

    week_48 = plan_jsearch(store, boards, now=datetime(2026, 11, 24, 9, tzinfo=timezone.utc))
    week_49 = plan_jsearch(store, boards, now=datetime(2026, 12, 1, 9, tzinfo=timezone.utc))

    assert {b.board_slug for b in week_48.boards}.isdisjoint(
        {b.board_slug for b in week_49.boards}
    )


def test_no_api_key_means_no_calls(store, monkeypatch):
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    plan = plan_jsearch(store, [jsearch_board()], now=NOW)

    assert plan.boards == [] and "JSEARCH_API_KEY" in (plan.note or "")


def test_row_ceiling_stops_a_runaway(store, budget, monkeypatch):
    monkeypatch.setenv("JSEARCH_MAX_ROWS", "1")
    store.save_board_jobs(
        jsearch_board(),
        [Job(url="https://example.test/1", title="Engineer", external_id="one")],
    )

    plan = plan_jsearch(store, [jsearch_board("another query")], now=NOW)

    assert plan.boards == [] and "row ceiling" in (plan.note or "")


def test_pages_are_counted_as_requests(store, budget, monkeypatch):
    monkeypatch.setenv("JSEARCH_WEEKLY_REQUESTS", "4")
    board = jsearch_board("software engineer jobs in chicago", num_pages=3)

    plan = plan_jsearch(store, [board], now=NOW)

    assert plan.requests == 3
