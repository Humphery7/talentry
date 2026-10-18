import pytest

from talentry_crawler.models import Board


@pytest.fixture
def board() -> Board:
    return Board(
        company_slug="acme",
        board_slug="acme-greenhouse",
        board_url="https://job-boards.greenhouse.io/acme",
        monitor_type="greenhouse",
        monitor_config={"token": "acme"},
    )
