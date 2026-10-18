"""The adapters, tested against fake API replies (no internet needed)."""

import httpx
import pytest

from talentry_crawler.ats import ashby, get_discoverer, greenhouse, lever
from talentry_crawler.models import Board


def client_replying(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_greenhouse_turns_escaped_html_back_into_html(board):
    def reply(request):
        assert request.url.path == "/v1/boards/acme/jobs"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                        "title": "  Backend   Engineer ",
                        "content": "&lt;p&gt;Build things &amp;amp; ship&lt;/p&gt;",
                        "location": {"name": "Lagos"},
                        "offices": [{"name": "Lagos"}, {"name": "Remote"}],
                        "first_published": "2026-01-02T00:00:00Z",
                    }
                ]
            },
        )

    async with client_replying(reply) as client:
        [job] = await greenhouse.discover(board, client)

    assert job.title == "Backend Engineer"
    assert job.description == "<p>Build things &amp; ship</p>"
    assert job.locations == ["Lagos", "Remote"]


async def test_greenhouse_unknown_board_says_gone(board):
    async with client_replying(lambda r: httpx.Response(404)) as client:
        with pytest.raises(LookupError, match="board gone"):
            await greenhouse.discover(board, client)


async def test_ashby_reads_jobs():
    board = Board("acme", "acme-ashby", "https://jobs.ashbyhq.com/acme", "ashby")

    def reply(request):
        assert request.url.path.endswith("/job-board/acme")
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "jobUrl": "https://jobs.ashbyhq.com/acme/1",
                        "title": "Designer",
                        "descriptionHtml": "<p>Hi</p>",
                        "location": "Remote",
                        "secondaryLocations": [{"location": "Berlin"}],
                        "employmentType": "FullTime",
                    },
                    {"title": "Has no url, skipped"},
                ]
            },
        )

    async with client_replying(reply) as client:
        jobs = await ashby.discover(board, client)

    assert [j.title for j in jobs] == ["Designer"]
    assert jobs[0].locations == ["Remote", "Berlin"]


async def test_lever_follows_pages_until_a_short_page(monkeypatch):
    async def no_pause(_seconds):  # skip the polite 0.5s wait between pages
        pass

    monkeypatch.setattr(lever.asyncio, "sleep", no_pause)

    board = Board("acme", "acme-lever", "https://jobs.lever.co/acme", "lever")
    full_page = [{"hostedUrl": f"https://jobs.lever.co/acme/{i}", "text": f"Job {i}"} for i in range(100)]
    last_page = [{"hostedUrl": "https://jobs.lever.co/acme/last", "text": "Last"}]
    pages = {"0": full_page, "100": last_page}

    async with client_replying(lambda r: httpx.Response(200, json=pages[r.url.params["skip"]])) as client:
        jobs = await lever.discover(board, client)

    assert len(jobs) == 101


def test_registry_lookup_error_lists_what_is_supported():
    with pytest.raises(KeyError, match="greenhouse"):
        get_discoverer("workday")
