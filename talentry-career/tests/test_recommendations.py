from uuid import uuid4

import routes.recommendations as routes
from services.recommendations import _candidates


class FakeCursor:
    def __init__(self) -> None:
        self.sql: str | None = None
        self.params: tuple | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params

    def fetchall(self):
        return []


class FakeConn:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()

    def cursor(self, **_kwargs):
        return self.cursor_obj


def _capture_refresh(monkeypatch):
    calls: list[dict | None] = []
    monkeypatch.setattr(routes.ai_keys, "require_key", lambda conn, user_id: "key")
    monkeypatch.setattr(
        routes,
        "refresh_recommendations",
        lambda conn, user_id, api_key=None, filters=None: (
            calls.append(filters) or 1
        ),
    )
    return calls


def test_refresh_without_a_body_keeps_the_saved_scope(monkeypatch):
    calls = _capture_refresh(monkeypatch)

    result = routes.refresh_user(uuid4(), FakeConn(), None)

    assert calls == [None]
    assert result.count == 1


def test_refresh_without_a_filters_key_keeps_the_saved_scope(monkeypatch):
    calls = _capture_refresh(monkeypatch)

    routes.refresh_user(uuid4(), FakeConn(), routes.RefreshRequest())

    assert calls == [None]


def test_refresh_with_an_explicit_empty_scope_clears_it(monkeypatch):
    calls = _capture_refresh(monkeypatch)

    routes.refresh_user(uuid4(), FakeConn(), routes.RefreshRequest(filters={}))

    assert calls == [{}]


def test_refresh_with_filters_saves_the_new_scope(monkeypatch):
    calls = _capture_refresh(monkeypatch)

    routes.refresh_user(
        uuid4(), FakeConn(), routes.RefreshRequest(filters={"loc": ["europe"]})
    )

    assert calls == [{"loc": ["europe"]}]


def test_candidates_exclude_the_previous_recommendations():
    conn = FakeConn()

    _candidates(conn, uuid4(), None, exclude=[4, 5])

    assert conn.cursor_obj.sql is not None
    assert "jobs.id <> ALL(%s)" in conn.cursor_obj.sql
    assert [4, 5] in conn.cursor_obj.params


def test_candidates_do_not_exclude_when_there_is_no_previous_list():
    conn = FakeConn()

    _candidates(conn, uuid4(), None)

    assert conn.cursor_obj.sql is not None
    assert "jobs.id <> ALL(%s)" not in conn.cursor_obj.sql
