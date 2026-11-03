from contextlib import nullcontext
from uuid import uuid4

from services.profile_embeddings import refresh_profile_embedding


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql, params=None):
        self.params = params

    def fetchone(self):
        return self.row


class FakeConn:
    def __init__(self, row):
        self.row = row
        self.update = None

    def cursor(self, **_kwargs):
        return FakeCursor(self.row)

    def transaction(self):
        return nullcontext()

    def execute(self, sql, params=None):
        self.update = (sql, params)


def test_profile_is_embedded_and_saved():
    user_id = uuid4()
    conn = FakeConn(
        {
            "headline": "Backend Engineer",
            "current_title": "Engineer",
            "years_experience": 3,
            "location": "Remote",
            "summary": None,
            "cv_data": "Built APIs.",
        }
    )
    prompts = []

    def embedder(text):
        prompts.append(text)
        return [0.1] * 384

    assert refresh_profile_embedding(conn, user_id, embedder) is True
    assert "Headline: Backend Engineer" in prompts[0]
    assert conn.update[1][1] == user_id
    assert conn.update[1][0].startswith("[0.1,")
    assert "::vector" in conn.update[0]


def test_missing_profile_is_not_updated():
    conn = FakeConn(None)

    assert refresh_profile_embedding(conn, uuid4(), lambda text: [0.1]) is None
    assert conn.update is None


def test_empty_profile_clears_the_vector():
    conn = FakeConn(
        {
            "headline": None,
            "current_title": None,
            "years_experience": None,
            "location": None,
            "summary": None,
            "cv_data": None,
        }
    )

    assert refresh_profile_embedding(conn, uuid4(), lambda text: [0.1]) is False
    assert conn.update[1][0] is None
