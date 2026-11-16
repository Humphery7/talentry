from types import SimpleNamespace
from uuid import UUID

from services.agent_applications import store


class FakeCursor:
    def __init__(self, row: dict | None) -> None:
        self.row = row

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: object = None) -> None:
        self.sql = sql

    def fetchone(self) -> dict | None:
        return self.row


class FakeConn:
    """Just enough of psycopg's connection for store.answer()."""

    def __init__(self, row: dict | None) -> None:
        self.row = row
        self.calls: list[tuple[str, object]] = []

    def cursor(self, row_factory: object = None) -> FakeCursor:
        return FakeCursor(self.row)

    def execute(self, sql: str, params: object = None) -> SimpleNamespace:
        self.calls.append((sql, params))
        return SimpleNamespace(rowcount=1)


def application_row(*attention: dict) -> dict:
    return {"status": "needs_input", "attention": list(attention)}


def test_answer_key_is_the_normalised_question():
    assert store.answer_key({"label": "Current company"}) == "q:current company"
    assert (
        store.answer_key({"question": "What should I put for “Phone”?"})
        == "q:what should i put for phone"
    )
    assert store.answer_key({"fact_key": "phone"}) == "fact:phone"


def test_sensitive_answers_are_not_reusable():
    assert store.reusable({"label": "Current company"}) is True
    assert store.reusable({"label": "Work authorization"}) is False
    assert store.reusable({"label": "Salary expectation"}) is False
    assert store.reusable({"label": "Notice period"}) is False
    assert store.reusable({"label": "Current company", "sensitive": True}) is False


def test_sensitive_answer_stays_on_the_application_only():
    row = application_row(
        {
            "id": "company",
            "kind": "question",
            "label": "Current company",
            "question": "What should I put for “Current company”?",
            "answer": None,
        },
        {
            "id": "salary",
            "kind": "question",
            "label": "Salary expectation",
            "question": "What should I put for “Salary expectation”?",
            "sensitive": True,
            "answer": None,
        },
    )
    conn = FakeConn(row)

    answered = store.answer(
        conn,
        UUID(int=1),
        UUID(int=2),
        {"company": "Glovo", "salary": "50000"},
    )

    assert answered == 2
    inserts = [
        params
        for sql, params in conn.calls
        if "INSERT INTO applicant_answers" in sql
    ]
    assert [params[1] for params in inserts] == ["q:current company"]
    # Both answers are still on the application, so a retry is not asked again.
    assert {item["id"]: item["answer"] for item in row["attention"]} == {
        "company": "Glovo",
        "salary": "50000",
    }


def test_fact_answers_use_the_stable_fact_key():
    row = application_row(
        {
            "id": "phone",
            "kind": "question",
            "label": "Phone",
            "question": "What should I put for “Phone”?",
            "fact_key": "phone",
            "answer": None,
        }
    )
    conn = FakeConn(row)

    store.answer(conn, UUID(int=1), UUID(int=2), {"phone": "+1 555 0100"})

    inserts = [
        params
        for sql, params in conn.calls
        if "INSERT INTO applicant_answers" in sql
    ]
    assert [params[1] for params in inserts] == ["fact:phone"]


def test_missing_setup_only_requires_the_cv():
    assert store.missing_setup(
        FakeConn({"cv_data": "CV"}),
        UUID(int=1),
    ) == []
    # Phone and location are collected on the questions screen when a form
    # needs them, so they do not block queueing.
    assert store.missing_setup(
        FakeConn({"cv_data": "CV", "phone": None, "location": None}),
        UUID(int=1),
    ) == []
    assert store.missing_setup(FakeConn(None), UUID(int=1)) == ["your CV"]


def test_document_pdf_returns_the_stored_file():
    conn = FakeConn({"version": 2, "pdf": memoryview(b"%PDF-1.7 cv")})

    assert store.document_pdf(
        conn, UUID(int=1), UUID(int=2), "cv", 2
    ) == (2, b"%PDF-1.7 cv")


def test_document_pdf_is_none_when_no_file_is_stored():
    # Cover letters and hand-edited versions have text but no generated PDF.
    assert (
        store.document_pdf(
            FakeConn({"version": 3, "pdf": None}),
            UUID(int=1),
            UUID(int=2),
            "cover_letter",
        )
        is None
    )
    assert (
        store.document_pdf(
            FakeConn(None), UUID(int=1), UUID(int=2), "cv"
        )
        is None
    )


def code_row(status: str) -> dict:
    return {
        "status": status,
        "attention": [
            {
                "id": "code",
                "kind": "code",
                "question": "Security code",
                "answer": None,
            }
        ],
    }


def test_code_answer_keeps_the_page_held_and_is_never_banked():
    row = code_row("awaiting_code")
    conn = FakeConn(row)

    answered = store.answer(
        conn, UUID(int=1), UUID(int=2), {"code": "12345678"}
    )

    assert answered == 1
    assert row["attention"][0]["answer"] == "12345678"
    # The worker is polling this row with its browser still open, so the
    # status must not change to 'queued'.
    assert any(
        "AND status = 'awaiting_code'" in sql for sql, _ in conn.calls
    )
    # A one-time code must never reach the answer bank.
    assert not any(
        "INSERT INTO applicant_answers" in sql for sql, _ in conn.calls
    )


def test_code_answer_is_refused_when_no_page_is_being_held():
    import pytest

    conn = FakeConn(code_row("needs_input"))

    with pytest.raises(store.InvalidState):
        store.answer(conn, UUID(int=1), UUID(int=2), {"code": "12345678"})
