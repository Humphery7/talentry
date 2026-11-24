"""The pre-insert guard: an aggregator copy must not create a second row.

Just as important are the cases that must NOT be dropped: a second real
requisition with the same title and city, a different team, a different city,
and a company we do not crawl.
"""

import re

import httpx
import pytest

from talentry_crawler.config import load_label_dictionaries
from talentry_crawler.labeling import Labeler
from talentry_crawler.models import Board, Company, Job
from talentry_crawler.pipeline import crawl_one_board
from talentry_crawler.pipeline.duplicate_guard import (
    EmployerIndex,
    cities,
    drop_employer_copies,
    normalize_name,
    normalize_title,
)
from talentry_crawler.storage import JobStore

NOTION = [Company(slug="notion", name="Notion")]
SCRIBD = [Company(slug="scribd", name="Scribd")]


# ---- normalisation --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Scribd, Inc.", "scribd"),
        ("Crunchyroll, LLC", "crunchyroll"),
        ("Canonical Ltd", "canonical"),
        ("Notion", "notion"),
        ("AT&T", "at t"),
        ("Siemens AG", "siemens"),
        ("", ""),
        (None, ""),
    ],
)
def test_company_name_is_reduced_to_its_core(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Software Engineer", "software engineer"),
        ("  Senior   Backend Engineer  ", "senior backend engineer"),
        ("Grainger is hiring: Software Engineer in Chicago", "software engineer in chicago"),
        (
            "Junior Software Test Engineer (Java, AWS, SQL) - 897",
            "junior software test engineer java aws sql",
        ),
        ("Sr Software Engineer(c# &.Net)", "sr software engineer c# .net"),
    ],
)
def test_titles_are_compared_without_publisher_decoration(raw, expected):
    assert normalize_title(raw) == expected


def test_only_the_city_part_of_a_location_counts():
    assert cities(["San Francisco, California", "New York, New York"]) == {
        "san francisco",
        "new york",
    }
    assert cities(None) == set()


# ---- fixtures -------------------------------------------------------------


@pytest.fixture
def store(tmp_path):
    s = JobStore(tmp_path / "jobs.db")
    yield s
    s.close()


@pytest.fixture(scope="module")
def labeler():
    return Labeler(load_label_dictionaries())


def employer_board(slug="notion", monitor="ashby") -> Board:
    return Board(
        company_slug=slug,
        board_slug=f"{slug}-{monitor}",
        board_url=f"https://example.test/{slug}",
        monitor_type=monitor,
        monitor_config={},
    )


def employer_job(
    n: int,
    title="Software Engineer, Collections Infra",
    city="San Francisco, California",
) -> Job:
    return Job(
        url=f"https://jobs.ashbyhq.com/notion/{n}", title=title, locations=[city]
    )


def aggregator_job(
    title="Software Engineer, Collections Infra",
    city="San Francisco, CA",
    company="Notion",
    url="https://www.indeed.com/viewjob?jk=1",
) -> Job:
    return Job(
        url=url,
        title=title,
        locations=[city],
        # The adapter slugifies the raw employer name, so "Scribd, Inc."
        # becomes "scribd-inc", which is not a slug we know.
        company_slug=re.sub(r"[^a-z0-9]+", "-", company.lower()).strip("-"),
        company_name=company,
        external_id=f"uid-{abs(hash(url)) % 10**8}",
    )


def seed(store, jobs, slug="notion"):
    store.save_board_jobs(employer_board(slug), jobs)


# ---- the guard ------------------------------------------------------------


def test_a_unique_employer_posting_makes_the_aggregator_copy_redundant(store):
    seed(store, [employer_job(1)])

    kept, dropped = drop_employer_copies([aggregator_job()], store, EmployerIndex(NOTION))

    assert (len(kept), dropped) == (0, 1)


def test_a_name_with_a_legal_suffix_still_finds_the_company(store):
    """JSearch says 'Scribd, Inc.' (slug 'scribd-inc'); companies.csv says 'scribd'."""
    seed(store, [employer_job(1)], slug="scribd")

    kept, dropped = drop_employer_copies(
        [aggregator_job(company="Scribd, Inc.")], store, EmployerIndex(SCRIBD)
    )

    assert (len(kept), dropped) == (0, 1)


def test_two_real_requisitions_with_the_same_title_and_city_are_never_collapsed(store):
    """Accenture has 1,004 identical rows in Pune: a match is only trusted when unique."""
    seed(store, [employer_job(1), employer_job(2)])

    kept, dropped = drop_employer_copies([aggregator_job()], store, EmployerIndex(NOTION))

    assert (len(kept), dropped) == (1, 0)


def test_a_different_team_at_the_same_level_is_a_different_job(store):
    """Real case: Crunchyroll 'Software Engineer III, Web and Connected' next to
    'Software Engineer III, Media Delivery' in the same city."""
    seed(store, [employer_job(1, title="Software Engineer III, Media Delivery")])

    kept, dropped = drop_employer_copies(
        [aggregator_job(title="Software Engineer III, Web and Connected")],
        store,
        EmployerIndex(NOTION),
    )

    assert (len(kept), dropped) == (1, 0)


def test_the_same_title_in_another_city_is_a_different_job(store):
    seed(store, [employer_job(1, city="New York, New York")])

    kept, dropped = drop_employer_copies(
        [aggregator_job(city="San Francisco, CA")], store, EmployerIndex(NOTION)
    )

    assert (len(kept), dropped) == (1, 0)


def test_a_job_open_in_two_cities_matches_either_one(store):
    seed(store, [employer_job(1, city="San Francisco, California")])
    seed(
        store,
        [
            Job(
                url="https://jobs.ashbyhq.com/notion/2",
                title="Software Engineer, Collections Infra",
                locations=["New York, New York"],
            )
        ],
    )

    kept, dropped = drop_employer_copies(
        [aggregator_job(city="New York, NY")], store, EmployerIndex(NOTION)
    )

    assert (len(kept), dropped) == (0, 1)


def test_a_company_we_do_not_crawl_is_kept(store):
    kept, dropped = drop_employer_copies(
        [aggregator_job(company="Grainger")], store, EmployerIndex(NOTION)
    )

    assert (len(kept), dropped) == (1, 0)


def test_another_aggregator_row_is_not_evidence(store):
    store.save_board_jobs(
        Board(
            company_slug="jsearch",
            board_slug="jsearch-software-engineer-san-francisco",
            board_url="https://api.openwebninja.com/jsearch/search-v2",
            monitor_type="jsearch",
            monitor_config={"query": "q"},
        ),
        [
            Job(
                url="https://jooble.org/1",
                title="Software Engineer, Collections Infra",
                locations=["San Francisco, CA"],
            )
        ],
    )

    kept, dropped = drop_employer_copies([aggregator_job()], store, EmployerIndex(NOTION))

    assert (len(kept), dropped) == (1, 0)


def test_a_job_publisher_decorated_the_title_around(store):
    """'Notion is hiring: Software Engineer, Collections Infra' is the same job."""
    seed(store, [employer_job(1)])

    kept, dropped = drop_employer_copies(
        [aggregator_job(title="Notion is hiring: Software Engineer, Collections Infra")],
        store,
        EmployerIndex(NOTION),
    )

    assert (len(kept), dropped) == (0, 1)


# ---- wiring ---------------------------------------------------------------


def fake_embedder(texts):
    return [[0.1] * 384 for _ in texts]


async def test_an_employer_board_never_drops_its_own_second_requisition(
    store, labeler, monkeypatch
):
    """The guard only runs for aggregators, so two identical requisitions on an
    employer's own board are both stored."""
    from talentry_crawler.pipeline import crawl

    board = employer_board("notion", "greenhouse")

    def two_requisitions():
        return [
            Job(
                url=f"https://boards.greenhouse.io/notion/jobs/{n}",
                title="Software Engineer, Collections Infra",
                locations=["San Francisco, California"],
            )
            for n in (1, 2)
        ]

    async def discover(board, client):
        return two_requisitions()

    monkeypatch.setattr(crawl, "get_discoverer", lambda monitor_type: discover)

    async with httpx.AsyncClient() as client:
        result = await crawl_one_board(
            board,
            client,
            labeler,
            store,
            embedder=fake_embedder,
            employer_index=EmployerIndex(NOTION),
        )

    assert (result.inserted, result.duplicates) == (2, 0)


async def test_aggregator_pass_skips_what_the_employer_board_already_stored(
    monkeypatch, tmp_path
):
    """End to end through crawl_boards: the aggregator runs after the employer
    boards, so it recognises the copy even though its URL is different."""
    from talentry_crawler.pipeline import crawl

    monkeypatch.setenv("JSEARCH_API_KEY", "test-key")
    monkeypatch.setattr(crawl, "load_companies", lambda: [Company(slug="notion", name="Notion")])

    employer = employer_board()
    aggregator = Board(
        company_slug="jsearch",
        board_slug="jsearch-notion",
        board_url="https://api.openwebninja.com/jsearch/search-v2",
        monitor_type="jsearch",
        monitor_config={"query": "notion software engineer", "num_pages": 1},
    )

    async def discover(board, client):
        if board.monitor_type == "jsearch":
            return [
                Job(
                    url="https://www.indeed.com/viewjob?jk=1",
                    title="Software Engineer, Collections Infra",
                    locations=["San Francisco, CA"],
                    company_slug="notion",
                    company_name="Notion",
                    external_id="uid-1",
                )
            ]
        return [
            Job(
                url="https://jobs.ashbyhq.com/notion/1",
                title="Software Engineer, Collections Infra",
                locations=["San Francisco, California"],
            )
        ]

    class NullLabeler:
        def label(self, job):
            return None

    monkeypatch.setattr(crawl, "get_discoverer", lambda monitor_type: discover)
    monkeypatch.setattr(crawl, "load_boards", lambda **kw: [employer, aggregator])
    monkeypatch.setattr(crawl, "Labeler", lambda dictionaries: NullLabeler())

    results = await crawl.crawl_boards(
        ats=["ashby", "jsearch"],
        db_path=tmp_path / "jobs.db",
        embedder=fake_embedder,
    )

    by_type = {r.monitor_type: r for r in results}
    assert by_type["ashby"].inserted == 1
    assert (by_type["jsearch"].inserted, by_type["jsearch"].duplicates) == (0, 1)

    store = JobStore(tmp_path / "jobs.db")
    try:
        rows = store._conn.execute("SELECT url FROM jobs").fetchall()
        assert [row["url"] for row in rows] == ["https://jobs.ashbyhq.com/notion/1"]
    finally:
        store.close()
