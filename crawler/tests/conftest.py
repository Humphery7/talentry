import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "talentry_embeddings"))

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
