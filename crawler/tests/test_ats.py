"""The adapters, tested against fake API replies (no internet needed)."""

import json
from urllib.parse import parse_qs

import httpx
import pytest

from talentry_crawler.ats import (
    accenture,
    almacareer,
    amazon,
    ashby,
    bamboohr,
    beehire,
    beisen,
    brassring,
    bytedance,
    cnstaff,
    comeet,
    cornerstone,
    curately,
    deel,
    dvinci,
    earcu,
    fenbi,
    gem,
    get_discoverer,
    greenhouse,
    hibob,
    hirehive,
    hireology,
    jarvi,
    job51,
    keka,
    lever,
    manatal,
    nowhiring,
    paynet,
    personio,
    pinpoint,
    recruitee,
    recruiter_co_kr,
    seamlesshiring,
    talentreef,
    traffit,
    turbohire,
    universia,
    wecruit,
    welcometothejungle,
    woowa,
)
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


async def test_pinpoint_reads_full_posting():
    board = Board(
        "acme",
        "acme-pinpoint",
        "https://acme.pinpointhq.com",
        "pinpoint",
        {"slug": "acme"},
    )

    def reply(request):
        assert request.url.path == "/postings.json"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "url": "https://acme.pinpointhq.com/postings/1",
                        "title": "  Platform   Engineer ",
                        "description": "<p>Build things</p>",
                        "benefits": "<p>Perks</p>",
                        "benefits_header": "Benefits",
                        "location": {"name": "Berlin"},
                        "employment_type": "full_time",
                        "workplace_type": "hybrid",
                        "created_at": "2026-01-02T00:00:00Z",
                        "compensation_minimum": 50000,
                        "compensation_maximum": 70000,
                        "compensation_currency": "EUR",
                        "compensation_frequency": "annual",
                        "compensation_visible": True,
                        "job": {
                            "department": {"name": "Engineering"},
                            "division": {"name": "Product"},
                            "requisition_id": "REQ-1",
                        },
                    }
                ]
            },
        )

    async with client_replying(reply) as client:
        [job] = await pinpoint.discover(board, client)

    assert job.title == "Platform Engineer"
    assert job.description == "<p>Build things</p>\n<h3>Benefits</h3>\n<p>Perks</p>"
    assert job.locations == ["Berlin"]
    assert job.employment_type == "full_time"
    assert job.workplace_type == "hybrid"
    assert job.salary == {"currency": "EUR", "min": 50000, "max": 70000, "unit": "year"}
    assert job.metadata == {
        "department": "Engineering",
        "division": "Product",
        "requisition_id": "REQ-1",
    }


async def test_recruitee_reads_full_offer():
    board = Board(
        "acme",
        "acme-recruitee",
        "https://acme.recruitee.com",
        "recruitee",
        {"slug": "acme"},
    )

    def reply(request):
        assert request.url.path == "/api/offers"
        return httpx.Response(
            200,
            json={
                "offers": [
                    {
                        "careers_url": "https://acme.recruitee.com/o/engineer",
                        "title": "Engineer",
                        "description": "<p>Role</p>",
                        "requirements": "<p>Skills</p>",
                        "locations": [{"city": "Berlin", "country": "Germany"}],
                        "employment_type_code": "fulltime_permanent",
                        "hybrid": True,
                        "published_at": "2026-01-02T00:00:00Z",
                        "salary": {
                            "min": 50000,
                            "max": 70000,
                            "currency": "EUR",
                            "period": "yearly",
                        },
                        "department": "Engineering",
                        "tags": ["python"],
                        "id": 10,
                    }
                ]
            },
        )

    async with client_replying(reply) as client:
        [job] = await recruitee.discover(board, client)

    assert job.title == "Engineer"
    assert job.description == "<p>Role</p>\n<p>Skills</p>"
    assert job.locations == ["Berlin, Germany"]
    assert job.employment_type == "fulltime_permanent"
    assert job.workplace_type == "hybrid"
    assert job.salary == {"currency": "EUR", "min": 50000, "max": 70000, "unit": "year"}
    assert job.metadata == {"department": "Engineering", "tags": ["python"], "id": 10}


async def test_gem_reads_full_posting():
    board = Board(
        "acme",
        "acme-gem",
        "https://jobs.gem.com/acme",
        "gem",
        {"token": "acme"},
    )

    def reply(request):
        assert request.url.path == "/job_board/v0/acme/job_posts/"
        return httpx.Response(
            200,
            json=[
                {
                    "absolute_url": "https://jobs.gem.com/acme/1",
                    "title": "Designer",
                    "content": "<p>Design</p>",
                    "offices": [
                        {"location": {"name": "Remote"}},
                        {"name": "Berlin"},
                    ],
                    "employment_type": "full_time",
                    "location_type": "remote",
                    "first_published_at": "2026-01-02T00:00:00Z",
                    "departments": [{"name": "Design"}, {"name": "Product"}],
                }
            ],
        )

    async with client_replying(reply) as client:
        [job] = await gem.discover(board, client)

    assert job.title == "Designer"
    assert job.description == "<p>Design</p>"
    assert job.locations == ["Remote", "Berlin"]
    assert job.employment_type == "full_time"
    assert job.workplace_type == "remote"
    assert job.metadata == {"department": "Design, Product"}


async def test_personio_reads_xml_feed():
    board = Board(
        "acme",
        "acme-personio",
        "https://acme.jobs.personio.de/",
        "personio",
        {"slug": "acme", "language": "en"},
    )
    xml = """\
<workzag-jobs>
  <position>
    <id>1</id>
    <name>Engineer</name>
    <office>Berlin</office>
    <department>Engineering</department>
    <employmentType>permanent</employmentType>
    <schedule>full-time</schedule>
    <createdAt>2026-01-02T00:00:00Z</createdAt>
    <jobDescriptions>
      <jobDescription><name>Role</name><value>&lt;p&gt;Build things&lt;/p&gt;</value></jobDescription>
    </jobDescriptions>
  </position>
</workzag-jobs>
"""

    def reply(request):
        assert request.url.host == "acme.jobs.personio.de"
        assert request.url.path == "/xml"
        assert request.url.params["language"] == "en"
        return httpx.Response(200, text=xml)

    async with client_replying(reply) as client:
        [job] = await personio.discover(board, client)

    assert job.url == "https://acme.jobs.personio.de/job/1"
    assert job.title == "Engineer"
    assert job.description == "<h3>Role</h3>\n<p>Build things</p>"
    assert job.locations == ["Berlin"]
    assert job.employment_type == "full-time"
    assert job.metadata["department"] == "Engineering"


async def test_personio_falls_back_to_embedded_listing():
    board = Board(
        "acme",
        "acme-personio",
        "https://acme.jobs.personio.de/",
        "personio",
        {"slug": "acme"},
    )
    page = (
        '<script>self.__next_f.push([1,"{\\"jobs\\": [{\\"id\\": 7, '
        '\\"name\\": \\"Engineer\\", \\"main_office\\": \\"Berlin\\", '
        '\\"employment_type\\": \\"permanent\\", \\"schedule\\": \\"full-time\\", '
        '\\"created_at\\": \\"2026-01-02T00:00:00Z\\"}], '
        '\\"subdomain\\": \\"acme\\"}"])</script>'
    )

    def reply(request):
        if request.url.path == "/xml":
            return httpx.Response(404)
        assert request.url.path == "/"
        return httpx.Response(200, text=page)

    async with client_replying(reply) as client:
        [job] = await personio.discover(board, client)

    assert job.url == "https://acme.jobs.personio.de/job/7"
    assert job.title == "Engineer"
    assert job.locations == ["Berlin"]
    assert job.employment_type == "full-time"


async def test_deel_reads_full_posting():
    board = Board(
        "acme",
        "acme-deel",
        "https://jobs.deel.com/acme",
        "deel",
        {"slug": "acme", "org_id": "org", "board_id": "board"},
    )

    def reply(request):
        assert request.url.path == "/guest/ats/organizations/org/job_boards/board/job_postings"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "posting-1",
                    "title": "Engineer",
                    "richtextDescription": "<p>Build things</p>",
                    "createdAt": "2026-01-02T00:00:00Z",
                    "isCompensationVisible": True,
                    "job": {
                        "jobLocations": [{"location": {"name": "Paris"}}],
                        "jobEmploymentTypes": [
                            {"employmentType": {"name": "Full-time"}}
                        ],
                        "jobTeams": [{"team": {"name": "Platform"}}],
                        "jobDepartments": [{"department": {"name": "Engineering"}}],
                        "currentCompensation": {
                            "minAmount": 50000,
                            "maxAmount": 70000,
                            "currencyIsoCode": "EUR",
                        },
                    },
                }
            ],
        )

    async with client_replying(reply) as client:
        [job] = await deel.discover(board, client)

    assert job.url == "https://jobs.deel.com/acme/job-details/posting-1/overview"
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Paris"]
    assert job.employment_type == "Full-time"
    assert job.salary == {"currency": "EUR", "min": 50000, "max": 70000, "unit": "year"}
    assert job.metadata == {"id": "posting-1", "team": "Platform", "department": "Engineering"}


async def test_hirehive_paginates_and_reads_full_posting():
    board = Board(
        "acme",
        "acme-hirehive",
        "https://acme.hirehive.com/",
        "hirehive",
        {"slug": "acme", "defaults": {"job_location_type": "hybrid"}},
    )

    def reply(request):
        assert request.url.path == "/api/v2/jobs"
        assert request.url.params["page"] == "1"
        assert request.url.params["page_size"] == "100"
        return httpx.Response(
            200,
            json={
                "meta": {"has_next_page": False},
                "items": [
                    {
                        "id": "job_1",
                        "hosted_url": "https://acme.hirehive.com/job/1",
                        "title": "Engineer",
                        "description": {"html": "<p>Build things</p>"},
                        "location": "Munich",
                        "type": {"type": "Full-time"},
                        "published_date": "2026-01-02T00:00:00Z",
                        "compensation_tiers": [
                            {
                                "min_value": 50000,
                                "max_value": 70000,
                                "currency_code": "EUR",
                                "interval": "yearly",
                            }
                        ],
                        "category": {"name": "Engineering"},
                        "experience": {"type": "Senior"},
                    }
                ],
            },
        )

    async with client_replying(reply) as client:
        [job] = await hirehive.discover(board, client)

    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Munich"]
    assert job.employment_type == "Full-time"
    assert job.workplace_type == "hybrid"
    assert job.salary == {"currency": "EUR", "min": 50000, "max": 70000, "unit": "year"}
    assert job.metadata == {
        "id": "job_1",
        "category": "Engineering",
        "experience": "Senior",
    }


async def test_traffit_reads_full_posting():
    board = Board(
        "acme",
        "acme-traffit",
        "https://acme.traffit.com/career/",
        "traffit",
        {"slug": "acme"},
    )

    def reply(request):
        assert request.url.path == "/public/job_posts/published"
        assert request.headers["X-Request-Page-Size"] == "100"
        assert request.headers["X-Request-Current-Page"] == "1"
        return httpx.Response(
            200,
            headers={"x-result-total-pages": "1"},
            json=[
                {
                    "url": "https://acme.traffit.com/public/an/1",
                    "advert": {
                        "name": "Engineer",
                        "values": [
                            {"field_id": "description", "value": "<p>Build things</p>"},
                            {
                                "field_id": "geolocation",
                                "value": '{"locality": "Warsaw", "country": "Poland"}',
                            },
                        ],
                        "recruitment": {"nr_ref": "REF-1"},
                    },
                    "options": {
                        "job_type": ["Full time"],
                        "remote": "1",
                        "_Salary_MIN": "1000",
                        "_Salary_MAX": "2000",
                        "_Salary_Currency": "PLN",
                        "_Salary_Rate": "Monthly",
                        "branches": "Engineering",
                    },
                    "valid_start": "2026-01-02 00:00:00",
                }
            ],
        )

    async with client_replying(reply) as client:
        [job] = await traffit.discover(board, client)

    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Warsaw, Poland"]
    assert job.employment_type == "Full time"
    assert job.workplace_type == "remote"
    assert job.date_posted == "2026-01-02"
    assert job.salary == {"currency": "PLN", "min": 1000.0, "max": 2000.0, "unit": "month"}
    assert job.metadata == {"reference": "REF-1", "department": "Engineering"}


async def test_manatal_reads_full_posting():
    board = Board(
        "acme",
        "acme-manatal",
        "https://www.careers-page.com/acme",
        "manatal",
        {"slug": "acme"},
    )

    def reply(request):
        assert request.url.path == "/api/v1.0/c/acme/jobs/"
        assert request.url.params["page"] == "1"
        assert request.url.params["page_size"] == "50"
        return httpx.Response(
            200,
            json={
                "count": 1,
                "next": None,
                "results": [
                    {
                        "id": 1,
                        "hash": "ABC123",
                        "position_name": "Engineer",
                        "description": "<p>Build things</p>",
                        "location_display": "Berlin, Germany",
                    }
                ],
            },
        )

    async with client_replying(reply) as client:
        [job] = await manatal.discover(board, client)

    assert job.url == "https://www.careers-page.com/acme/job/ABC123"
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Berlin, Germany"]
    assert job.metadata == {"id": 1}


def test_registry_lookup_error_lists_what_is_supported():
    with pytest.raises(KeyError, match="greenhouse"):
        get_discoverer("workday")


def test_new_providers_are_registered():
    assert get_discoverer("pinpoint") is pinpoint.discover
    assert get_discoverer("recruitee") is recruitee.discover
    assert get_discoverer("gem") is gem.discover
    assert get_discoverer("personio") is personio.discover
    assert get_discoverer("deel") is deel.discover
    assert get_discoverer("hirehive") is hirehive.discover
    assert get_discoverer("traffit") is traffit.discover
    assert get_discoverer("manatal") is manatal.discover
    assert get_discoverer("bamboohr") is bamboohr.discover
    assert get_discoverer("hibob") is hibob.discover
    assert get_discoverer("recruiter_co_kr") is recruiter_co_kr.discover
    assert get_discoverer("talentreef") is talentreef.discover
    assert get_discoverer("cornerstone") is cornerstone.discover
    assert get_discoverer("beehire") is beehire.discover
    assert get_discoverer("seamlesshiring") is seamlesshiring.discover
    assert get_discoverer("cnstaff") is cnstaff.discover
    assert get_discoverer("paynet") is paynet.discover
    assert get_discoverer("universia") is universia.discover
    assert get_discoverer("comeet") is comeet.discover
    assert get_discoverer("jarvi") is jarvi.discover
    assert get_discoverer("keka") is keka.discover
    assert get_discoverer("nowhiring") is nowhiring.discover
    assert get_discoverer("turbohire") is turbohire.discover
    assert get_discoverer("amazon") is amazon.discover
    assert get_discoverer("curately") is curately.discover
    assert get_discoverer("job51") is job51.discover
    assert get_discoverer("welcometothejungle") is welcometothejungle.discover
    assert get_discoverer("woowa") is woowa.discover


async def test_bamboohr_reads_listing_and_detail():
    board = Board(
        "acme",
        "acme-bamboohr",
        "https://acme.bamboohr.com/careers",
        "bamboohr",
        {"tenant": "acme"},
    )

    def reply(request):
        if request.url.path == "/careers/list":
            return httpx.Response(
                200,
                json={
                    "meta": {"totalCount": 1},
                    "result": [
                        {
                            "id": "148",
                            "jobOpeningName": "Engineer",
                            "departmentId": "21012",
                            "departmentLabel": "Platform",
                            "employmentStatusLabel": "Permanent",
                            "location": {
                                "city": "Dublin",
                                "state": "Leinster",
                                "addressCountry": "Ireland",
                            },
                        }
                    ],
                },
            )
        assert request.url.path == "/careers/148/detail"
        return httpx.Response(
            200,
            json={
                "result": {
                    "jobOpening": {
                        "jobOpeningName": "Platform Engineer",
                        "description": "<p>Build things</p>",
                        "datePosted": "2026-01-02",
                        "locationType": "2",
                        "minimumExperience": "Mid",
                    }
                }
            },
        )

    async with client_replying(reply) as client:
        [job] = await bamboohr.discover(board, client)

    assert job.url == "https://acme.bamboohr.com/careers/148"
    assert job.title == "Platform Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Dublin, Leinster, Ireland"]
    assert job.employment_type == "Permanent"
    assert job.workplace_type == "hybrid"
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "job_id": "148",
        "department": "Platform",
        "department_id": "21012",
        "minimum_experience": "Mid",
    }


async def test_hibob_reads_full_posting():
    board = Board(
        "acme",
        "acme-hibob",
        "https://acme.careers.hibob.com/jobs",
        "hibob",
    )

    def reply(request):
        assert request.url.path == "/api/job-ad"
        assert request.headers["Referer"] == "https://acme.careers.hibob.com/"
        return httpx.Response(
            200,
            json={
                "jobAdDetails": [
                    {
                        "id": "job-1",
                        "title": "Engineer",
                        "description": "<p>Role</p>",
                        "responsibilities": "<p>Build</p>",
                        "requirements": "<p>Python</p>",
                        "benefits": "<p>Equity</p>",
                        "site": "Berlin",
                        "employmentTypeId": "Permanent",
                        "workspaceType": "Hybrid",
                        "publishedAt": "2026-01-02T00:00:00Z",
                        "payTransparencyMinSalary": 50000,
                        "payTransparencyMaxSalary": 70000,
                        "payTransparencySalaryCurrency": "EUR",
                        "payTransparencySalaryPayPeriod": "annual",
                        "department": "Engineering",
                        "departmentId": "dep-1",
                        "language": "en",
                    }
                ]
            },
        )

    async with client_replying(reply) as client:
        [job] = await hibob.discover(board, client)

    assert job.url == "https://acme.careers.hibob.com/jobs/job-1"
    assert job.title == "Engineer"
    assert job.description == (
        "<p>Role</p>\n"
        "<h3>Responsibilities</h3>\n<p>Build</p>\n"
        "<h3>Requirements</h3>\n<p>Python</p>\n"
        "<h3>Benefits</h3>\n<p>Equity</p>"
    )
    assert job.locations == ["Berlin"]
    assert job.employment_type == "Permanent"
    assert job.workplace_type == "hybrid"
    assert job.salary == {"currency": "EUR", "min": 50000, "max": 70000, "unit": "year"}
    assert job.metadata == {
        "id": "job-1",
        "department": "Engineering",
        "department_id": "dep-1",
        "employment_type_id": "Permanent",
    }


async def test_recruiter_co_kr_reads_list_and_detail():
    board = Board(
        "acme",
        "acme-recruiter",
        "https://acme.recruiter.co.kr/career/home",
        "recruiter_co_kr",
        {"slug": "acme"},
    )

    def reply(request):
        assert request.headers["prefix"] == "acme.recruiter.co.kr"
        if request.method == "POST":
            assert request.url.path == "/position/v1/jobflex"
            body = json.loads(request.content)
            assert body["filter"]["openStatusList"] == ["OPEN"]
            return httpx.Response(
                200,
                json={
                    "pagination": {"totalPages": 1, "totalCount": 1},
                    "list": [
                        {
                            "positionSn": 123,
                            "title": "Engineer",
                            "startDateTime": "2026-01-02T12:00:00",
                            "careerType": "CAREER",
                            "classificationCode": "Headquarters",
                            "tagList": [{"tagName": "Backend"}],
                        }
                    ],
                },
            )
        assert request.url.path == "/position/v2/jobflex/123"
        return httpx.Response(
            200,
            json={
                "title": "Platform Engineer",
                "jobDescription": "<p>Build things</p>",
                "jobDescriptionType": "HTML",
                "startDateTime": "2026-01-02T12:00:00",
                "endDateTime": "2026-02-01T00:00:00",
                "careerType": "CAREER",
                "classificationCode": "Headquarters",
                "tagList": [{"tagName": "Backend"}],
                "regionNameList": ["Seoul"],
                "announcementType": "REGULAR",
                "recruitmentType": "EXPERIENCED",
            },
        )

    async with client_replying(reply) as client:
        [job] = await recruiter_co_kr.discover(board, client)

    assert job.url == "https://acme.recruiter.co.kr/career/jobs/123"
    assert job.title == "Platform Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Seoul"]
    assert job.employment_type == "CAREER"
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "position_sn": 123,
        "classification": "Headquarters",
        "tags": ["Backend"],
        "valid_through": "2026-01-31",
        "announcement_type": "REGULAR",
        "recruitment_type": "EXPERIENCED",
    }


async def test_talentreef_reads_career_page_and_search():
    board = Board(
        "acme",
        "acme-talentreef",
        "https://apply.jobappnetwork.com/acme/en",
        "talentreef",
        {"alias": "acme", "locale": "en"},
    )

    def reply(request):
        if request.method == "GET":
            assert request.url.path == "/apply/careerPages/alias/acme"
            return httpx.Response(
                200,
                json=[
                    {
                        "clientId": "18746",
                        "locale": "en",
                        "brands": ["Acme"],
                        "published": True,
                    }
                ],
            )
        assert request.url.path == "/apply/proxy-es/search-en-us/posting/_search"
        body = json.loads(request.content)
        filters = body["query"]["bool"]["filter"]
        assert {"terms": {"clientId.raw": ["18746"]}} in filters
        assert {"terms": {"brand.raw": ["Acme"]}} in filters
        return httpx.Response(
            200,
            json={
                "hits": {
                    "total": {"value": 1},
                    "hits": [
                        {
                            "_source": {
                                "jobId": 42,
                                "positionType": "Engineer",
                                "description": "<p>Build things</p>",
                                "address": {"city": "Austin", "country": "US"},
                                "category": "Engineering",
                                "createdDate": "2026-01-02T00:00:00Z",
                                "postingUuid": "uuid-1",
                                "brand": "Acme",
                                "clientName": "Acme Inc",
                            }
                        }
                    ],
                }
            },
        )

    async with client_replying(reply) as client:
        [job] = await talentreef.discover(board, client)

    assert job.url == "https://apply.jobappnetwork.com/clients/18746/posting/42/en"
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Austin, US"]
    assert job.employment_type == "Engineering"
    assert job.metadata == {
        "job_id": 42,
        "posting_uuid": "uuid-1",
        "brand": "Acme",
        "client_name": "Acme Inc",
    }


async def test_cornerstone_bootstraps_and_reads_search():
    board = Board(
        "acme",
        "acme-cornerstone",
        "https://acme.csod.com/ux/ats/careersite/4/home?c=acme",
        "cornerstone",
        {"tenant": "acme", "site_id": 4, "corp": "acme"},
    )
    token = f"{'a' * 24}.{'b' * 24}.{'c' * 24}"
    context = {
        "corp": "acme",
        "token": token,
        "cultureID": 1,
        "cultureName": "en-US",
        "endpoints": {"cloud": "https://eu-fra.api.csod.com/"},
    }
    page = f"<script>csod.context={json.dumps(context)};</script>"

    def reply(request):
        if request.method == "GET":
            assert request.url.path == "/ux/ats/careersite/4/home"
            return httpx.Response(200, text=page)
        assert request.url.path == "/rec-job-search/external/jobs"
        assert request.headers["Authorization"] == f"Bearer {token}"
        body = json.loads(request.content)
        assert body["careerSiteId"] == 4
        assert body["pageNumber"] == 1
        return httpx.Response(
            200,
            json={
                "status": "Success",
                "data": {
                    "totalCount": 1,
                    "requisitions": [
                        {
                            "requisitionId": 273622,
                            "displayJobTitle": "Engineer",
                            "externalDescription": "<p>Build things</p>",
                            "postingEffectiveDate": "01/02/2026",
                            "locations": [
                                {"city": "Paris", "state": "IDF", "country": "FR"}
                            ],
                        }
                    ],
                },
            },
        )

    async with client_replying(reply) as client:
        [job] = await cornerstone.discover(board, client)

    assert job.url == (
        "https://acme.csod.com/ux/ats/careersite/4/home/requisition/273622?c=acme"
    )
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Paris, IDF, FR"]
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {"requisition_id": 273622}


async def test_beehire_reads_public_campaigns():
    board = Board(
        "acme",
        "acme-beehire",
        "https://app.beehire.com/career/acme",
        "beehire",
    )

    def reply(request):
        assert request.url.path == "/users/getPublicCampaigns/acme"
        return httpx.Response(
            200,
            json={
                "campaigns": [
                    {
                        "_id": "campaign-1",
                        "title": {"0": "Platform Engineer"},
                        "fullDescription": {"0": "<p>Build things</p>"},
                        "inviteLink": "/career/acme/job/abc",
                        "inviteKey": "abc",
                        "deadline": "2026-02-01",
                        "location": {"name": "Paris"},
                        "jobCategories": [{"label": "Engineering"}],
                        "details": {
                            "contract": {
                                "type": "contractType_permanent",
                                "duration": "contractDuration_fullTime",
                                "remote": "remoteWork_hybrid",
                            }
                        },
                    }
                ]
            },
        )

    async with client_replying(reply) as client:
        [job] = await beehire.discover(board, client)

    assert job.url == "https://app.beehire.com/career/acme/job/abc"
    assert job.title == "Platform Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Paris"]
    assert job.employment_type == "permanent"
    assert job.workplace_type == "hybrid"
    assert job.metadata == {
        "id": "campaign-1",
        "invite_key": "abc",
        "deadline": "2026-02-01",
        "categories": ["Engineering"],
    }


async def test_seamlesshiring_reads_job_list():
    board = Board(
        "acme",
        "acme-seamlesshiring",
        "https://acme.seamlesshiring.com/jobs",
        "seamlesshiring",
    )

    def reply(request):
        assert request.url.path == "/v2/jobs/job-list"
        assert request.url.params["limit"] == "100"
        assert request.url.params["page"] == "1"
        return httpx.Response(
            200,
            json={
                "data": {
                    "jobs": {
                        "data": [
                            {
                                "id": 42,
                                "title": "Engineer",
                                "summary": "<p>Build things</p>",
                                "details": "<p>Ship them</p>",
                                "location": "Lagos",
                                "job_type": "Full-time",
                                "work_style": "Remote",
                                "post_date": "2026-01-02",
                                "expiry_date": "2026-02-01",
                                "position": "Senior",
                            }
                        ],
                        "total": 1,
                        "next_page_url": None,
                    }
                }
            },
        )

    async with client_replying(reply) as client:
        [job] = await seamlesshiring.discover(board, client)

    assert job.url == "https://acme.seamlesshiring.com/job/view/42"
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>\n<p>Ship them</p>"
    assert job.locations == ["Lagos"]
    assert job.employment_type == "Full-time"
    assert job.workplace_type == "remote"
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "id": 42,
        "position": "Senior",
        "valid_through": "2026-02-01",
    }


async def test_cnstaff_reads_job_list():
    board = Board(
        "acme",
        "acme-cnstaff",
        "https://acme.cnstaff.com/recruit",
        "cnstaff",
    )

    def reply(request):
        assert request.url.path == "/recruit"
        assert request.url.params["n"] == "1"
        assert request.url.params["p"] == "1"
        return httpx.Response(
            200,
            json={
                "total": 1,
                "page": {"now": 1, "total": 1, "pageSize": 15},
                "list": [
                    {
                        "job_id": "100",
                        "job_name_show": "Engineer",
                        "job_detail": "Build\nthings",
                        "job_desc2": "Python",
                        "job_address_name": "Shanghai",
                        "job_published_at": "2026-01-02 09:00:00",
                        "job_end_at": "2026-02-01 00:00:00",
                        "company_orgnize_name_show": "Acme",
                        "g_job_type": "Engineering",
                    }
                ],
            },
        )

    async with client_replying(reply) as client:
        [job] = await cnstaff.discover(board, client)

    assert job.url == "https://acme.cnstaff.com/recruitment/job/detail/id/100/"
    assert job.title == "Engineer"
    assert job.description == (
        "<h3>Responsibilities</h3>\n<p>Build<br>things</p>\n"
        "<h3>Qualifications</h3>\n<p>Python</p>"
    )
    assert job.locations == ["Shanghai"]
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "id": "100",
        "employer": "Acme",
        "job_function": "Engineering",
        "valid_through": "2026-02-01",
    }


async def test_paynet_reads_public_postings():
    board = Board(
        "acme",
        "acme-paynet",
        "https://www.pay-netonline.com/PayNet/Applicant/Postings.aspx?co=ACME",
        "paynet",
    )
    posting_id = "123e4567-e89b-12d3-a456-426614174000"

    def reply(request):
        assert request.url.path == "/applicantpublic/jobpostings"
        assert request.url.params["company_id"] == "ACME"
        return httpx.Response(
            200,
            json=[
                {
                    "ID": posting_id,
                    "Company": {"Name": "Acme"},
                    "Position": {
                        "Title": "Engineer",
                        "Description": "<p>Build things</p>",
                        "Requirements": "<p>Python</p>",
                        "Location": "Austin, TX",
                        "StartDate": "01/02/2026",
                        "EndDate": "02/01/2026",
                    },
                }
            ],
        )

    async with client_replying(reply) as client:
        [job] = await paynet.discover(board, client)

    assert job.url == (
        "https://www.pay-netonline.com/PayNet/Applicant/Posting.aspx?"
        f"JobPostingID={posting_id}"
    )
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>\n<h3>Requirements</h3>\n<p>Python</p>"
    assert job.locations == ["Austin, TX"]
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "posting_id": posting_id,
        "company_id": "ACME",
        "company_name": "Acme",
        "valid_through": "2026-02-01",
        "qualifications": "<p>Python</p>",
    }


async def test_universia_resolves_board_and_reads_postings():
    board = Board(
        "acme",
        "acme-universia",
        "https://jobboard.universia.net/acme",
        "universia",
        {"language": "es"},
    )
    board_id = "80aad5c7-634e-4127-a715-6984ff63555b"
    job_id = "c2e3f4a5-1111-4222-8333-444455556666"

    def reply(request):
        if request.url.path == "/empleo/entities/v2/jobboard/slug/acme/config/":
            assert request.url.params["status"] == "published"
            return httpx.Response(
                200,
                json={
                    "slug": "acme",
                    "languages": ["es-ES"],
                    "entity": {"id": board_id, "entityType": "company"},
                },
            )
        assert request.url.path == "/orientacion-job-posting/v1/api/job-posting"
        assert request.url.params["offset"] == "0"
        assert request.url.params["limit"] == "100"
        assert request.url.params.get_list("postingType") == ["job", "internship"]
        assert request.url.params["boards"] == board_id
        return httpx.Response(
            200,
            json={
                "offset": 0,
                "limit": 100,
                "size": 1,
                "total": 1,
                "totalPages": 1,
                "results": [
                    {
                        "identifier": job_id,
                        "boards": [board_id],
                        "status": "published",
                        "title": "Engineer",
                        "description": "<p>Build things</p>",
                        "requirements": "<p>Python</p>",
                        "incentiveCompensation": "<p>Degree</p>",
                        "validThrough": "2026-02-01",
                        "postingType": "job",
                        "employmentType": "Full-time",
                        "jobLocationType": "remote",
                        "datePosted": "2026-01-02",
                        "url": (
                            f"https://www.universia.net/co/empleo/{job_id}/"
                            f"engineer.html?referer={board_id}"
                        ),
                        "jobLocation": {
                            "address": {
                                "addressLocality": "Bogota",
                                "addressCountry": "CO",
                            }
                        },
                    }
                ],
            },
        )

    async with client_replying(reply) as client:
        [job] = await universia.discover(board, client)

    assert job.url == (
        f"https://www.universia.net/co/empleo/{job_id}/"
        f"engineer.html?referer={board_id}"
    )
    assert job.title == "Engineer"
    assert job.description == (
        "<p>Build things</p>\n<h3>Requirements</h3>\n<p>Python</p>\n"
        "<h3>Education</h3>\n<p>Degree</p>"
    )
    assert job.locations == ["Bogota, CO"]
    assert job.employment_type == "Full-time"
    assert job.workplace_type == "remote"
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "universia_job_id": job_id,
        "universia_board_id": board_id,
        "posting_type": "job",
        "qualifications": "<p>Python</p><p>Degree</p>",
        "valid_through": "2026-02-01",
        "language": "es",
    }


async def test_comeet_reads_embedded_positions():
    board = Board(
        "acme",
        "acme-comeet",
        "https://www.comeet.com/jobs/acme/C6.001",
        "comeet",
        {"company": "acme", "board_id": "C6.001"},
    )
    positions = [
        {
            "name": "Engineer",
            "uid": "56.371",
            "company_name": "Acme",
            "department": "Engineering",
            "url_active_page": "https://acme.example/careers/56.371",
            "employment_type": "Full-time",
            "workplace_type": "Hybrid",
            "time_updated": "2026-01-02T00:00:00Z",
            "location": {"name": "Tel Aviv", "is_remote": True},
            "custom_fields": {
                "details": [
                    {
                        "name": "Description",
                        "value": "<p>Build things</p>",
                        "order": 1,
                    },
                    {
                        "name": "Requirements",
                        "value": "<p>Python</p>",
                        "order": 2,
                    },
                    {
                        "name": "Responsibilities",
                        "value": "<p>Ship things</p>",
                        "order": 3,
                    },
                ]
            },
        }
    ]

    def reply(request):
        assert request.url.path == "/jobs/acme/C6.001"
        return httpx.Response(
            200,
            text=f"<script>COMPANY_POSITIONS_DATA = {json.dumps(positions)};</script>",
        )

    async with client_replying(reply) as client:
        [job] = await comeet.discover(board, client)

    assert job.url == "https://acme.example/careers/56.371"
    assert job.title == "Engineer"
    assert job.description == (
        "<h3>Description</h3>\n<p>Build things</p>\n"
        "<h3>Requirements</h3>\n<p>Python</p>\n"
        "<h3>Responsibilities</h3>\n<p>Ship things</p>"
    )
    assert job.locations == ["Tel Aviv"]
    assert job.employment_type == "Full-time"
    assert job.workplace_type == "hybrid"
    assert job.date_posted == "2026-01-02T00:00:00Z"
    assert job.metadata == {
        "uid": "56.371",
        "department": "Engineering",
        "company_name": "Acme",
        "time_updated": "2026-01-02T00:00:00Z",
        "qualifications": "<p>Python</p>",
        "responsibilities": "<p>Ship things</p>",
    }


async def test_jarvi_reads_public_offers():
    board = Board(
        "acme",
        "acme-jarvi",
        "https://acme.example/careers",
        "jarvi",
        {"public_api_key": "key-1", "currency": "EUR"},
    )

    def field(purpose, *, value=None, choice=None, location=None):
        return {
            "field": {"purpose": purpose},
            "value": value,
            "fieldValue": {"technicalValue": choice} if choice else None,
            "location": location,
        }

    offer = {
        "id": "offer-1",
        "shortId": "short-1",
        "name": "<p>Engineer</p>",
        "publishedAt": "2026-01-02T00:00:00Z",
        "updatedAt": "2026-01-03T00:00:00Z",
        "fieldsValues": [
            field("joboffer_title", value="<p>Platform Engineer</p>"),
            field("joboffer_contract_type", choice="permanent"),
            field("joboffer_is_fulltime", value="true"),
            field(
                "joboffer_company_description",
                value="<p>Acme builds things.</p>",
            ),
            field("joboffer_description", value="<p>Build things.</p>"),
            field("joboffer_profile_description", value="<p>Python.</p>"),
            field(
                "joboffer_location",
                location={"formattedAddress": "Paris, France"},
            ),
            field("joboffer_salary_is_public", value="true"),
            field("joboffer_salary_per_year_min", value="50000"),
            field("joboffer_salary_per_year_max", value="70000"),
            field("joboffer_remote_days_per_week", value="3"),
            field("joboffer_min_years_of_experience", value="5"),
        ],
    }

    def reply(request):
        assert request.url.path == "/v1/public-api/rest/v2/offers"
        assert request.url.params["limit"] == "50000"
        assert request.headers["x-api-key"] == "key-1"
        return httpx.Response(200, json={"data": [offer], "total": 1})

    async with client_replying(reply) as client:
        [job] = await jarvi.discover(board, client)

    assert job.url == "https://acme.example/careers?q=short-1%2Fplatform-engineer"
    assert job.title == "Platform Engineer"
    assert job.description == (
        "<p>Acme builds things.</p>\n<p>Build things.</p>\n<p>Python.</p>"
    )
    assert job.locations == ["Paris, France"]
    assert job.employment_type == "permanent"
    assert job.workplace_type == "hybrid"
    assert job.date_posted == "2026-01-02T00:00:00Z"
    assert job.salary == {"currency": "EUR", "min": 50000, "max": 70000, "unit": "year"}
    assert job.metadata == {
        "source_id": "offer-1",
        "short_id": "short-1",
        "updated_at": "2026-01-03T00:00:00Z",
        "minimum_years_experience": 5,
        "responsibilities": "<p>Build things.</p>",
        "qualifications": "<p>Python.</p>",
    }


async def test_keka_bootstraps_career_portal_and_reads_jobs():
    board = Board(
        "acme",
        "acme-keka",
        "https://acme.keka.com/careers",
        "keka",
    )
    identifier = "0e329376-fd32-40b6-afd2-d8fcbcd44435"

    def reply(request):
        if request.url.path == "/careers":
            return httpx.Response(
                200,
                text="<script>fetch('/ats/doc/careerportal/page.html')</script>",
            )
        if request.url.path == "/ats/doc/careerportal/page.html":
            return httpx.Response(
                200,
                text=(
                    "<script>window.khConfig = { identifier: "
                    f"'{identifier}', domain: 'https://acme.keka.com/careers/' }};"
                    "</script>"
                ),
            )
        assert request.url.path == f"/careers/api/embedjobs/default/active/{identifier}"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 42,
                    "title": "Engineer",
                    "description": "<div>Build <strong>things</strong></div>",
                    "departmentIdentifier": "dep-1",
                    "departmentName": "Engineering",
                    "jobLocations": [
                        {
                            "name": "Bengaluru",
                            "city": "Bengaluru",
                            "state": "Karnataka",
                            "countryName": "India",
                        }
                    ],
                    "jobType": 2,
                    "experience": "3+ years",
                    "jobNumber": "ACME-42",
                    "salaryRange": {
                        "minimum": 250000,
                        "maximum": 350000,
                        "currency": "INR",
                        "salaryPeriod": 0,
                    },
                    "publishedOn": "2026-01-02T00:00:00Z",
                    "skillNames": ["Python"],
                }
            ],
        )

    async with client_replying(reply) as client:
        [job] = await keka.discover(board, client)

    assert job.url == "https://acme.keka.com/careers/jobdetails/42"
    assert job.title == "Engineer"
    assert job.description == "<div>Build <strong>things</strong></div>"
    assert job.locations == ["Bengaluru, Karnataka, India"]
    assert job.employment_type == "Full Time"
    assert job.date_posted == "2026-01-02"
    assert job.salary == {
        "currency": "INR",
        "min": 250000,
        "max": 350000,
        "unit": None,
    }
    assert job.metadata == {
        "id": 42,
        "department_id": "dep-1",
        "department": "Engineering",
        "experience": "3+ years",
        "job_number": "ACME-42",
        "job_type": 2,
        "skills": ["Python"],
    }


async def test_nowhiring_searches_and_hydrates_details():
    board = Board(
        "acme",
        "acme-nowhiring",
        "https://nowhiring.com/acme/",
        "nowhiring",
    )

    def reply(request):
        if request.url.path.startswith("/api/career-live-sites/"):
            assert "%2F" in request.url.raw_path.decode()
            return httpx.Response(
                200,
                json={
                    "jobSearchCriteria": [
                        {"fieldName": "billingAccountId", "fieldValue": 123},
                        {"fieldName": "brandId", "fieldValue": "brand-1"},
                        {"fieldName": "brandTemplateId", "fieldValue": "template-1"},
                    ]
                },
            )
        if request.url.path == "/api/jobs/search":
            body = json.loads(request.content)
            assert body["start"] == "0"
            assert body["customerId"] == ["123"]
            return httpx.Response(
                200,
                json={"list": [{"id": "job-1"}], "total": 1},
            )
        assert request.url.path == "/api/jobs/job-1"
        return httpx.Response(
            200,
            json={
                "id": "job-1",
                "billingAccountId": 123,
                "jobTitle": "Engineer",
                "jobDescription": "<p>Build things</p>",
                "addressLine1": "1 Main St",
                "city": "Austin",
                "stateProvCode": "TX",
                "postalCode": "78701",
                "categories": ["Full-time"],
                "postedDate": "2026-01-02",
                "company": "Acme",
                "thirdPartyApplyUrl": "https://apply.example/job-1",
                "brandId": "brand-1",
            },
        )

    async with client_replying(reply) as client:
        [job] = await nowhiring.discover(board, client)

    assert job.url == "https://nowhiring.com/acme/job-details/job-1"
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["1 Main St, Austin, TX, 78701"]
    assert job.employment_type == "Full-time"
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "job_id": "job-1",
        "company": "Acme",
        "application_url": "https://apply.example/job-1",
        "brand_id": "brand-1",
    }


async def test_turbohire_reads_token_listing_and_details():
    board = Board(
        "acme",
        "acme-turbohire",
        "https://acme.turbohire.co/careerpage/"
        "4d757ba0-3d57-448a-b82c-238ed87ac90f",
        "turbohire",
    )

    def reply(request):
        if request.url.path == "/api/token/noauth":
            return httpx.Response(200, json={"access_token": "token-1"})
        if request.url.path == "/api/careerpagev2/filteredjobs":
            assert request.headers["authorization"] == "Bearer token-1"
            assert request.url.params["orgId"] == "4d757ba0-3d57-448a-b82c-238ed87ac90f"
            body = json.loads(request.content)
            assert body["Keyword"] == ""
            return httpx.Response(
                200,
                json={
                    "Total": 1,
                    "Result": [
                        {
                            "JobId": "job-1",
                            "JobIdObfuscated": "pub-1",
                            "JobTitle": "Engineer",
                        }
                    ],
                },
            )
        assert request.url.path == "/api/publicjobs"
        assert request.url.params["jobId"] == "pub-1"
        return httpx.Response(
            200,
            json={
                "JobId": "job-1",
                "JobIdObfuscated": "pub-1",
                "JobTitle": "Engineer",
                "JobCode": "ACME-1",
                "Department": "Engineering",
                "ClientName": "Acme",
                "JobDescription": "<p>Build things</p>",
                "Location": '[{"Address": "Austin, TX, US"}]',
                "Type": "UNSPECIFIED",
                "JobTypeV2": "Full Time",
                "PublishedDates": {"CAREERPAGE": "2026-01-02"},
                "Experience": {"MinExp": 3, "MaxExp": 5},
                "Skills": ["Python"],
                "RolesAndResponsibilitiesV2": "<p>Ship things</p>",
                "EligibilityV2": "<p>Python</p>",
            },
        )

    async with client_replying(reply) as client:
        [job] = await turbohire.discover(board, client)

    assert job.url == "https://acme.turbohire.co/job/publicjobs/pub-1"
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Austin, TX, US"]
    assert job.employment_type == "Full Time"
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "id": "job-1",
        "job_code": "ACME-1",
        "department": "Engineering",
        "client_name": "Acme",
        "experience_min": 3,
        "experience_max": 5,
        "skills": ["Python"],
        "responsibilities": "<p>Ship things</p>",
        "qualifications": "<p>Python</p>",
    }


async def test_amazon_reads_search_results():
    board = Board(
        "acme",
        "acme-amazon",
        "https://www.amazon.jobs/en/search",
        "amazon",
        {"country": "USA"},
    )

    def reply(request):
        assert request.url.path == "/en/search.json"
        assert request.url.params["country"] == "USA"
        assert request.url.params["result_limit"] == "100"
        assert request.url.params["sort"] == "recent"
        assert request.url.params["offset"] == "0"
        return httpx.Response(
            200,
            json={
                "hits": 1,
                "jobs": [
                    {
                        "job_path": "/en/jobs/42/engineer",
                        "title": "Engineer",
                        "description": "<p>Build things</p>",
                        "basic_qualifications": "<p>Python</p>",
                        "preferred_qualifications": "<p>AWS</p>",
                        "normalized_location": "Seattle, WA, USA",
                        "job_schedule_type": "Full-time",
                        "posted_date": "January  2, 2026",
                        "salary": "$120,000/year - $150,000/year",
                        "id_icims": "42",
                        "job_category": "Software Development",
                        "country_code": "USA",
                    }
                ],
            },
        )

    async with client_replying(reply) as client:
        [job] = await amazon.discover(board, client)

    assert job.url == "https://www.amazon.jobs/en/jobs/42/engineer"
    assert job.title == "Engineer"
    assert job.description == (
        "<p>Build things</p>\n"
        "<h3>Basic Qualifications</h3>\n<p>Python</p>\n"
        "<h3>Preferred Qualifications</h3>\n<p>AWS</p>"
    )
    assert job.locations == ["Seattle, WA, USA"]
    assert job.employment_type == "Full-time"
    assert job.date_posted == "2026-01-02"
    assert job.salary == {"currency": "USD", "min": 120000, "max": 150000, "unit": "year"}
    assert job.metadata == {
        "id_icims": "42",
        "job_category": "Software Development",
        "country_code": "USA",
    }


async def test_woowa_reads_listing_and_detail():
    board = Board(
        "acme",
        "acme-woowa",
        "https://career.woowahan.com/recruitment/",
        "woowa",
    )

    def reply(request):
        if request.url.path == "/w1/recruits":
            assert request.url.params["page"] == "0"
            assert request.url.params["size"] == "500"
            return httpx.Response(
                200,
                json={
                    "code": "2000",
                    "data": {
                        "totalSize": 1,
                        "list": [{"recruitNumber": "R-1"}],
                    },
                },
            )
        assert request.url.path == "/w1/recruits/R-1"
        return httpx.Response(
            200,
            json={
                "code": "2000",
                "data": {
                    "recruitNumber": "R-1",
                    "recruitName": "Platform Engineer",
                    "recruitContents": "<p>근무 지역: 서울 / 부산 역할: 백엔드</p>",
                    "employmentType": {"recruitItemCode": "BA002001"},
                    "recruitOpenDate": "2026-01-02 00:00:00",
                    "recruitEndDate": "2999-12-31 00:00:00",
                    "recruitCorporationNumber": "CORP-1",
                    "careerType": "experienced",
                    "jobGroup": "Engineering",
                },
            },
        )

    async with client_replying(reply) as client:
        [job] = await woowa.discover(board, client)

    assert job.url == "https://career.woowahan.com/recruitment/R-1/detail"
    assert job.title == "Platform Engineer"
    assert job.description == "<p>근무 지역: 서울 / 부산 역할: 백엔드</p>"
    assert job.locations == ["Seoul, South Korea", "Busan, South Korea"]
    assert job.employment_type == "full_time"
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "recruit_number": "R-1",
        "corporation": "CORP-1",
        "career_type": "experienced",
        "job_group": "Engineering",
    }


async def test_job51_reads_signed_listing_and_detail():
    board = Board(
        "acme",
        "acme-job51",
        "https://acme.51job.com/acmejob_list.html",
        "job51",
    )

    def reply(request):
        if request.url.path == "/acmejob_list.html":
            return httpx.Response(200, text="<script>var config = { ctmid: 12345 }</script>")
        if request.url.path == "/job_list.php":
            params = json.loads(request.url.params["params"])
            assert params["ctmid"] == 12345
            assert params["pagenum"] == 1
            return httpx.Response(
                200,
                text='jsoncallback({"status":"1","resultbody":'
                '{"totalnum":1,"joblist":[{"jobid":"123456"}]}})',
            )
        assert request.url.path == "/job_detail.php"
        assert json.loads(request.url.params["params"]) == {"jobid": "123456"}
        return httpx.Response(
            200,
            text='jsoncallback({"status":"1","resultbody":'
            '{"jobid":"123456","jobname":"Engineer","ctmid":12345,'
            '"jobinfo":"<p>Build things</p>岗位要求：<p>Python</p>",'
            '"jobareaname":"Shanghai","jkeyword":"Python SQL",'
            '"issuedate":"2026-01-02","term":"full_time",'
            '"coname":"Acme","divname":"Engineering"}})',
        )

    async with client_replying(reply) as client:
        [job] = await job51.discover(board, client)

    assert job.url == "https://jobs.51job.com/all/123456.html"
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>岗位要求：<p>Python</p>"
    assert job.locations == ["Shanghai"]
    assert job.employment_type == "full_time"
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "id": "123456",
        "employer": "Acme",
        "department": "Engineering",
        "skills": ["Python", "SQL"],
        "responsibilities": "<p>Build things</p>",
        "qualifications": "<p>Python</p>",
    }


async def test_welcometothejungle_reads_organization_and_algolia_jobs():
    board = Board(
        "acme",
        "acme-wttj",
        "https://www.welcometothejungle.com/en/companies/acme/jobs",
        "welcometothejungle",
    )

    def reply(request):
        if request.url.path == "/api/v1/organizations/acme":
            return httpx.Response(200, json={"organization": {"slug": "acme-org"}})
        if request.url.path == "/1/indexes/*/queries":
            body = json.loads(request.content)
            assert body["requests"][0]["indexName"] == "wk_cms_jobs_production"
            assert "organization.slug%3Aacme-org" in body["requests"][0]["params"]
            return httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "nbHits": 1,
                            "hits": [
                                {
                                    "slug": "platform-engineer",
                                    "reference": "ref-1",
                                    "website": {"reference": "acme"},
                                }
                            ],
                        }
                    ]
                },
            )
        assert request.url.path == "/api/v1/organizations/acme/jobs/platform-engineer"
        return httpx.Response(
            200,
            json={
                "job": {
                    "status": "published",
                    "slug": "platform-engineer",
                    "name": "Platform Engineer",
                    "description": "<p>Build things</p>",
                    "profile": "<p>Python</p>",
                    "key_missions": ["Ship things"],
                    "skills": [{"name": {"en": "Python"}}],
                    "offices": [{"local_address": "Paris, France"}],
                    "contract_type": "full_time",
                    "remote": "partial",
                    "published_at": "2026-01-02T00:00:00Z",
                    "salary_min": 50000,
                    "salary_max": 70000,
                    "salary_currency": "EUR",
                    "salary_period": "yearly",
                    "language": "en",
                    "reference": "ref-1",
                    "profession": {"name": {"en": "Engineering"}},
                }
            },
        )

    async with client_replying(reply) as client:
        [job] = await welcometothejungle.discover(board, client)

    assert job.url == (
        "https://www.welcometothejungle.com/en/companies/acme/jobs/platform-engineer"
    )
    assert job.title == "Platform Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Paris, France"]
    assert job.employment_type == "full_time"
    assert job.workplace_type == "hybrid"
    assert job.salary == {"currency": "EUR", "min": 50000, "max": 70000, "unit": "year"}
    assert job.metadata == {
        "reference": "ref-1",
        "profession": "Engineering",
    }


async def test_curately_reads_search_results():
    board = Board(
        "acme",
        "acme-curately",
        "https://careers.curately.ai/jobs/bms",
        "curately",
        {"currency": "USD", "salary_unit": "hour"},
    )

    def reply(request):
        if request.url.path == "/QADemoCurately/getByShortName/bms":
            return httpx.Response(
                200,
                json={
                    "Success": True,
                    "Status": 200,
                    "shortName": "bms",
                    "clientId": 7,
                },
            )
        assert request.url.path == "/QADemoCurately/sovrenjobsearch"
        body = json.loads(request.content)
        assert body["clientids"] == "7"
        assert body["next"] == 0
        return httpx.Response(
            200,
            json={
                "Success": True,
                "Status": 200,
                "TotalSize": 1,
                "List": [
                    {
                        "status": 1,
                        "jobId": 42,
                        "clientId": 7,
                        "jobTitle": "Engineer",
                        "publicJobDescr": "<p>Build things</p>",
                        "workCity": "Austin",
                        "workState": "TX",
                        "workZipcode": "78701",
                        "jobType": 1,
                        "jobHours": 1,
                        "workType": 2,
                        "createDate": "2026-01-02",
                        "payrateMin": 50,
                        "payrateMax": 70,
                        "clientName": "Acme",
                    }
                ],
            },
        )

    async with client_replying(reply) as client:
        [job] = await curately.discover(board, client)

    assert job.url == "https://careers.curately.ai/jobs/bms/apply-job/42/job"
    assert job.title == "Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Austin, TX, 78701"]
    assert job.employment_type == "full_time"
    assert job.workplace_type == "hybrid"
    assert job.date_posted == "2026-01-02"
    assert job.salary == {"currency": "USD", "min": 50, "max": 70, "unit": "hour"}
    assert job.metadata == {
        "id": 42,
        "client_name": "Acme",
        "job_hours_code": 1,
        "job_type_code": 1,
        "work_type_code": 2,
    }


async def test_accenture_reads_findjobs_api():
    board = Board(
        "acme",
        "acme-accenture",
        "https://www.accenture.com/sg-en/careers/jobsearch",
        "accenture",
        {"country": "Singapore", "language": "en", "site": "sg-en"},
    )

    def reply(request):
        assert request.url.path == "/api/accenture/elastic/findjobs"
        body = request.content.decode()
        assert 'name="startIndex"\r\n\r\n0' in body
        assert 'name="jobCountry"\r\n\r\nSingapore' in body
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "guid": "13475979_en",
                        "title": "Platform Engineer",
                        "jobDescription": "<p>Build things</p>",
                        "location": ["Singapore"],
                        "remoteType": "Hybrid",
                        "postedDate": "2026-01-02T00:00:00Z",
                        "businessArea": "Technology",
                        "careerLevel": "Senior Analyst",
                        "requisitionId": "R-1",
                    }
                ],
                "totalHits": {"total": 1, "overMaxHits": "False"},
            },
        )

    async with client_replying(reply) as client:
        [job] = await accenture.discover(board, client)

    assert job.url == "https://www.accenture.com/sg-en/careers/jobdetails?id=13475979_en"
    assert job.title == "Platform Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Singapore"]
    assert job.workplace_type == "hybrid"
    assert job.date_posted == "2026-01-02T00:00:00Z"
    assert job.metadata == {
        "guid": "13475979_en",
        "business_area": "Technology",
        "career_level": "Senior Analyst",
        "requisition_id": "R-1",
    }


async def test_beisen_reads_bootstrap_and_modern_listing():
    board = Board(
        "acme",
        "acme-beisen",
        "https://acme.zhiye.com/",
        "beisen",
    )
    portal_id = "4526ed81-8968-4d3d-bdc1-bb9a5c388cdf"
    job_id = "9280327e-6f59-4ce7-b184-5ac8428b725a"

    def reply(request):
        if request.method == "GET":
            assert request.url.path == "/"
            return httpx.Response(
                200,
                text=f'<script>var BSGlobal = {{"PortalId": "{portal_id}"}};</script>',
            )
        assert request.url.path == "/api/Jobad/GetJobAdPageList"
        body = json.loads(request.content)
        assert body["PageIndex"] == 0
        assert body["PortalId"] == portal_id
        return httpx.Response(
            200,
            json={
                "Code": 200,
                "Count": 1,
                "Data": [
                    {
                        "Id": job_id,
                        "JobAdId": 351617576,
                        "JobAdName": "HR Specialist",
                        "Category": "Campus",
                        "CategoryId": "2",
                        "Org": "Human Resources",
                        "OrgId": 10,
                        "LocNames": ["Hangzhou"],
                        "Salary": "Negotiable",
                        "Kind": "Full-time",
                        "PostDate": "2026-09-24T16:08:34",
                        "Duty": "Build teams\nHire people",
                        "Require": "Bachelor degree",
                        "Status": 1,
                    }
                ],
            },
        )

    async with client_replying(reply) as client:
        [job] = await beisen.discover(board, client)

    assert job.url == f"https://acme.zhiye.com/campus/detail?jobAdId={job_id}"
    assert job.title == "HR Specialist"
    assert job.locations == ["Hangzhou"]
    assert job.employment_type == "Full-time"
    assert job.date_posted == "2026-09-24"
    assert "<h3>工作职责</h3>" in job.description
    assert "<p>Build teams<br>Hire people</p>" in job.description
    assert "<h3>任职资格</h3>" in job.description
    assert job.metadata == {
        "id": job_id,
        "job_ad_id": 351617576,
        "category": "Campus",
        "category_id": "2",
        "organization": "Human Resources",
        "organization_id": 10,
        "salary": "Negotiable",
    }


async def test_almacareer_reads_graphql_listing_and_detail():
    board = Board(
        "acme",
        "acme-almacareer",
        "https://acme.jobs.cz/",
        "almacareer",
        {
            "widget_id": "c6d1f4e4-bdb0-49bb-9f87-7b6e729813fb",
            "api_key": "d" * 64,
        },
    )

    def reply(request):
        assert request.url.path == "/api/graphql/widget"
        body = json.loads(request.content)
        if "LISTING_QUERY" in body["query"]:
            assert body["variables"]["page"] == 1
            return httpx.Response(
                200,
                json={
                    "data": {
                        "widget": {
                            "jobAdList": {
                                "paginator": {"lastPage": 1},
                                "groupedJobAds": {
                                    "jobAds": [
                                        {
                                            "id": "job-1",
                                            "title": "Platform Engineer",
                                            "validFrom": "2026-01-02T09:00:00+01:00",
                                            "teaser": "<p>Short</p>",
                                            "locations": [
                                                {
                                                    "city": "Prague",
                                                    "country": "Czechia",
                                                }
                                            ],
                                            "salary": {
                                                "min": 50000,
                                                "max": 70000,
                                                "period": "rok",
                                                "currency": "CZK",
                                            },
                                            "employer": {"companyName": "Acme"},
                                            "parameters": {
                                                "employmentTypesObjects": [
                                                    {
                                                        "id": "201300001",
                                                        "label": "full-time",
                                                    }
                                                ]
                                            },
                                            "fieldsObjects": [{"id": "1", "label": "IT"}],
                                            "professionsObjects": [],
                                        }
                                    ],
                                    "groups": [],
                                },
                            }
                        }
                    }
                },
            )
        assert "JOB_DETAIL" in body["query"]
        assert body["variables"]["jobId"] == "job-1"
        return httpx.Response(
            200,
            json={
                "data": {
                    "widget": {
                        "jobAd": {
                            "id": "job-1",
                            "content": {"htmlContent": "<p>Full description</p>"},
                        }
                    }
                }
            },
        )

    async with client_replying(reply) as client:
        [job] = await almacareer.discover(board, client)

    assert job.url == "https://acme.jobs.cz/detail-pozice?r=detail&id=job-1"
    assert job.title == "Platform Engineer"
    assert job.description == "<p>Full description</p>"
    assert job.locations == ["Prague, Czechia"]
    assert job.employment_type == "full_time"
    assert job.date_posted == "2026-01-02"
    assert job.salary == {"currency": "CZK", "min": 50000, "max": 70000, "unit": "year"}
    assert job.metadata == {
        "id": "job-1",
        "country": "cz",
        "company_name": "Acme",
        "fields": ["IT"],
    }


async def test_wecruit_joins_public_lanes_and_details():
    suite = "670ca36b1c240e54e1ee0556"
    board = Board(
        "acme",
        "acme-wecruit",
        f"https://acme.example/SU{suite}/pb/index.html#/",
        "wecruit",
    )

    def reply(request):
        body = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        if request.url.path.endswith(f"/listPosition/SU{suite}"):
            if body["recruitType"] != "1":
                return httpx.Response(
                    200,
                    json={
                        "state": "200",
                        "data": {
                            "pageForm": {
                                "currentPage": 1,
                                "totalPage": 0,
                                "dataCount": 0,
                                "pageData": [],
                            }
                        },
                    },
                )
            return httpx.Response(
                200,
                json={
                    "state": "200",
                    "data": {
                        "pageForm": {
                            "currentPage": 1,
                            "totalPage": 1,
                            "dataCount": 1,
                            "pageData": [
                                {
                                    "postId": suite,
                                    "postName": "Platform Engineer",
                                    "recruitType": 1,
                                    "publishDate": "2026-01-02 09:00:00",
                                }
                            ],
                        }
                    },
                },
            )
        assert request.url.path.endswith(f"/listPositionDetail/SU{suite}")
        assert body == {"postId": suite}
        return httpx.Response(
            200,
            json={
                "state": "200",
                "data": {
                    "postId": suite,
                    "recruitType": 1,
                    "postName": "Platform Engineer",
                    "workContent": "Build things",
                    "serviceCondition": "Know Python",
                    "workPlaceList": [{"name": "Shanghai"}],
                    "publishDate": "2026-01-02 09:00:00",
                    "postCode": "P-1",
                    "company": "Acme",
                },
            },
        )

    async with client_replying(reply) as client:
        [job] = await wecruit.discover(board, client)

    assert job.url == (
        f"https://acme.example/SU{suite}/pb/posDetail.html?postId={suite}&postType=1"
    )
    assert job.title == "Platform Engineer"
    assert job.description == (
        "<h3>工作职责</h3>\n<p>Build things</p>\n"
        "<h3>任职要求</h3>\n<p>Know Python</p>"
    )
    assert job.locations == ["Shanghai"]
    assert job.date_posted == "2026-01-02"
    assert job.metadata == {
        "recruit_type": 1,
        "post_code": "P-1",
        "company": "Acme",
    }


async def test_hireology_reads_public_careers_api():
    board = Board(
        "acme",
        "acme-hireology",
        "https://careers.hireology.com/acme",
        "hireology",
    )

    def reply(request):
        assert request.url.path == "/v2/public/careers/acme"
        assert request.url.params["page_size"] == "500"
        assert request.url.params["page"] == "1"
        return httpx.Response(
            200,
            json={
                "count": 1,
                "data": [
                    {
                        "id": 42,
                        "status": "Open",
                        "career_site_url": "https://careers.hireology.com/acme/jobs/42",
                        "name": "Platform Engineer",
                        "job_description": "<p>Build things</p>",
                        "locations": [{"city": "Chicago", "state": "IL"}],
                        "employment_status": "Full-time",
                        "remote": True,
                        "created_at": "2026-01-02T00:00:00Z",
                        "organization": {"name": "Acme"},
                        "job_family": {"name": "Engineering"},
                    }
                ],
            },
        )

    async with client_replying(reply) as client:
        [job] = await hireology.discover(board, client)

    assert job.url == "https://careers.hireology.com/acme/jobs/42"
    assert job.title == "Platform Engineer"
    assert job.description == "<p>Build things</p>"
    assert job.locations == ["Chicago, IL"]
    assert job.employment_type == "Full-time"
    assert job.workplace_type == "remote"
    assert job.date_posted == "2026-01-02T00:00:00Z"
    assert job.metadata == {
        "organization": "Acme",
        "job_family": "Engineering",
        "id": 42,
    }


@pytest.mark.asyncio
async def test_brassring_paginates_and_validates_detail_identity() -> None:
    board_url = (
        "https://sjobs.brassring.com/TGnewUI/Search/Home/Home"
        "?partnerid=25416&siteid=6007"
    )

    def row(job_id: int, title: str, location: str) -> dict:
        return {
            "Link": (
                "https://sjobs.brassring.com/TGnewUI/Search/home/HomeWithPreLoad"
                f"?partnerid=25416&siteid=6007&PageType=JobDetails&jobid={job_id}"
            ),
            "Questions": [
                {"QuestionName": "reqid", "Value": str(job_id)},
                {"QuestionName": "jobtitle", "Value": title},
                {"QuestionName": "formtext8", "Value": location},
                {"QuestionName": "formtext10", "Value": "United States"},
                {"QuestionName": "lastupdated", "Value": "27-Oct-2026"},
                {"QuestionName": "department", "Value": "Engineering"},
                {"QuestionName": "formtext3", "Value": f"<p>{title}</p>"},
            ],
        }

    def payload(total: int, rows: list[dict]) -> dict:
        return {
            "JobsCount": total,
            "SortFields": [{"Name": "JobTitle", "Value": "Alphabetical"}],
            "Jobs": {"Job": rows},
        }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.path.endswith("/Search/Home/Home")
            return httpx.Response(
                200,
                text=(
                    '<input name="__RequestVerificationToken" value="token"/>'
                    '<input id="CookieValue" value="cookie"/>'
                ),
            )
        body = json.loads(request.content)
        if request.url.path.endswith("/Search/Ajax/MatchedJobs"):
            assert body["PartnerId"] == "25416"
            assert body["SiteId"] == "6007"
            assert body["encryptedsessionvalue"] == "cookie"
            assert request.headers["RFT"] == "token"
            return httpx.Response(200, json=payload(2, [row(42, "Engineer", "Austin")]))
        assert request.url.path.endswith("/Search/Ajax/ProcessSortAndShowMoreJobs")
        assert body["SortType"] == "JobTitle"
        page = body["pageNumber"]
        return httpx.Response(
            200,
            json=payload(2, [row(page, f"Engineer {page}", f"City {page}")]),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await brassring.discover(Board("acme", "Acme", board_url, "brassring"), client)

    assert [job.metadata["requisition_id"] for job in jobs] == ["1", "2"]
    assert [job.title for job in jobs] == ["Engineer 1", "Engineer 2"]
    assert jobs[0].locations == ["City 1, United States"]
    assert jobs[0].date_posted == "2026-10-27"
    assert jobs[0].description == "<p>Engineer 1</p>"
    assert jobs[0].metadata == {
        "provider": "brassring",
        "requisition_id": "1",
        "department": "Engineering",
    }


@pytest.mark.asyncio
async def test_bytedance_global_search() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/public/supplier/search/job/posts"
        assert request.headers["x-tt-env"] == "boe_epam_api"
        body = json.loads(request.content)
        assert body["limit"] == 1000
        assert body["offset"] == 0
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "count": 1,
                    "job_post_list": [
                        {
                            "id": "123",
                            "title": "Engineer",
                            "description": "<p>Build</p>",
                            "city_info": {"name": "London", "en_name": "London", "parent": {"name": "UK", "en_name": "UK"}},
                            "job_category": {"name": "Engineering"},
                            "recruit_type": {"name": "Full-Time"},
                            "create_time": "1770000000000",
                        }
                    ],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await bytedance.discover(
            Board("acme", "Acme", "https://joinbytedance.com/search", "bytedance"),
            client,
        )

    assert len(jobs) == 1
    assert jobs[0].url == "https://joinbytedance.com/search/123"
    assert jobs[0].locations == ["London, UK"]
    assert jobs[0].employment_type == "Full-Time"
    assert jobs[0].date_posted == "1770000000000"
    assert jobs[0].metadata == {"team": "Engineering"}


@pytest.mark.asyncio
async def test_bytedance_experienced_uses_filters() -> None:
    seen_filters = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_filters
        if request.method == "GET":
            seen_filters = True
            assert request.url.path == "/api/v1/config/job/filters/2"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "job_type_list": [{"id": "c1", "children": []}],
                        "job_type_count_map": {"c1": 1},
                    },
                },
            )
        body = json.loads(request.content)
        assert body["job_category_id_list"] == ["c1"]
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "count": 1,
                    "job_post_list": [
                        {
                            "id": "456",
                            "title": "Firmware Engineer",
                            "description": "<p>Firmware</p>",
                            "city_info": {
                                "name": "Shenzhen",
                                "en_name": "Shenzhen",
                                "parent": {"name": "China", "en_name": "China"},
                            },
                            "job_category": {"name": "Infrastructure"},
                            "recruit_type": {"name": "Full-Time"},
                        }
                    ],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await bytedance.discover(
            Board(
                "acme",
                "Acme",
                "https://jobs.bytedance.com/experienced/position",
                "bytedance",
            ),
            client,
        )

    assert seen_filters
    assert len(jobs) == 1
    assert jobs[0].url == "https://jobs.bytedance.com/experienced/position/456/detail"
    assert jobs[0].locations == ["Shenzhen, China"]
    assert jobs[0].employment_type == "Full-Time"
    assert jobs[0].metadata == {"team": "Infrastructure"}


@pytest.mark.asyncio
async def test_dvinci_parses_list_json() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "acme.dvinci-hr.com"
        assert request.url.path == "/jobPublication/list.json"
        return httpx.Response(
            200,
            json=[
                {
                    "id": 7,
                    "position": "Consultant",
                    "jobPublicationURL": "https://acme.dvinci-hr.com/en/jobs/consultant-7",
                    "introduction": "<p>Intro</p>",
                    "tasks": "<p>Tasks</p>",
                    "jobOpening": {
                        "locations": [{"name": "Paris"}],
                        "workingTimes": [{"internalName": "Full-time"}],
                        "createdDate": "2026-09-24T11:17:34.641Z",
                        "salary": {
                            "currency": "EUR",
                            "value": {
                                "minValue": 50000,
                                "maxValue": 60000,
                                "unitText": "YEAR",
                            },
                        },
                        "categories": [{"name": "Consulting"}],
                        "reference": "REF-7",
                    },
                }
            ],
        )

    board = Board("acme", "Acme", "https://acme.dvinci-hr.com/en/jobs", "dvinci")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await dvinci.discover(board, client)

    assert len(jobs) == 1
    assert jobs[0].title == "Consultant"
    assert jobs[0].locations == ["Paris"]
    assert jobs[0].employment_type == "Full-time"
    assert jobs[0].date_posted == "2026-09-24T11:17:34.641Z"
    assert jobs[0].salary == {"currency": "EUR", "unit": "year", "min": 50000, "max": 60000}
    assert jobs[0].description == "<p>Intro</p>\n<p>Tasks</p>"


@pytest.mark.asyncio
async def test_earcu_reads_xml_feed() -> None:
    feed = """<?xml version="1.0" encoding="utf-8"?>
<positions>
  <position>
    <VacancyRef>1426</VacancyRef>
    <JobTitle>Product Executive</JobTitle>
    <DescriptionURL>/jobs/vacancy/product-executive/1426/</DescriptionURL>
    <Description><![CDATA[<p>Role</p>]]></Description>
    <Locations><Location>Preston</Location></Locations>
    <JobFunction>Product</JobFunction>
    <Brand>Gold Medal</Brand>
    <DisplaySalaryDescription>Negotiable</DisplaySalaryDescription>
    <LastPublishedDate>2026-10-27T12:30:14.153</LastPublishedDate>
  </position>
</positions>"""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/jobs/allvacancies/"
        return httpx.Response(200, text=feed)

    board = Board(
        "acme",
        "Acme",
        "https://jobs.acme.example/jobs/vacancy/find/results/",
        "earcu",
        {"feed_url": "https://jobs.acme.example/jobs/allvacancies/"},
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await earcu.discover(board, client)

    assert len(jobs) == 1
    assert jobs[0].url == "https://jobs.acme.example/jobs/vacancy/product-executive/1426/"
    assert jobs[0].locations == ["Preston"]
    assert jobs[0].date_posted == "2026-10-27T12:30:14.153"
    assert jobs[0].metadata == {
        "reference": "1426",
        "job_function": "Product",
        "brand": "Gold Medal",
        "salary_description": "Negotiable",
    }


@pytest.mark.asyncio
async def test_fenbi_parses_embedded_bundle_inventory() -> None:
    bundle = """this.joinUsArr={
      "fulltime":[{
        "id":42,
        "title":"Backend Engineer",
        "publicDateShow":"2026年10月27日",
        "description":["Build things"],
        "requirements":["Python"],
        "location":"北京、杭州",
        "type":"Campus",
        "jobType":"fulltime"
      }],
      "parttime":[]
    };"""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/page/joinus":
            return httpx.Response(
                200,
                text='<script src="https://nodestatic.fbstatic.cn/weblts_spa_online/page/main-ABC123.js"></script>',
            )
        assert request.url.path == "/weblts_spa_online/page/main-ABC123.js"
        return httpx.Response(200, text=bundle)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await fenbi.discover(
            Board(
                "acme",
                "Acme",
                "https://www.fenbi.com/page/joinus",
                "fenbi",
                {"kind": "fulltime"},
            ),
            client,
        )

    assert len(jobs) == 1
    assert jobs[0].url == "https://www.fenbi.com/page/joinusdetail/fulltime/42"
    assert jobs[0].locations == ["北京", "杭州"]
    assert jobs[0].employment_type == "full_time"
    assert jobs[0].date_posted == "2026-10-27"
    assert jobs[0].description == (
        "<h2>岗位职责</h2><ol><li>Build things</li></ol>"
        "<h2>任职要求</h2><ol><li>Python</li></ol>"
    )
