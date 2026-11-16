from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from db.connect import ConnectionDep
from schemas.agent_applications import (
    AgentApplicationDetail,
    AgentApplicationDocument,
    AgentApplicationItem,
    AgentApplicationSummary,
    AnswerRequest,
    AnswerResult,
    StartRequest,
    StartResult,
)
from services import ai_keys
from services.agent_applications import JobsNotFound, enqueue
from services.agent_applications import store

router = APIRouter(prefix="/agent-applications", tags=["agent-applications"])


def _summary(row: dict) -> AgentApplicationSummary:
    return AgentApplicationSummary(
        id=row["id"],
        batchId=row["batch_id"],
        jobId=int(row["job_id"]),
        status=row["status"],
        platform=row.get("platform"),
        applyUrl=row.get("apply_url"),
        jobTitle=row.get("job_title"),
        company=row.get("company"),
        error=row.get("error"),
        warningCount=len(row.get("warnings") or []),
        attentionCount=sum(
            1
            for item in (row.get("attention") or [])
            if item.get("answer") is None
        ),
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
        approvedAt=row.get("approved_at"),
        submittedAt=row.get("submitted_at"),
        screenshot=row.get("screenshot"),
    )


def _detail(row: dict) -> AgentApplicationDetail:
    return AgentApplicationDetail(
        **_summary(row).model_dump(),
        plan=row.get("plan") or {},
        attention=row.get("attention") or [],
        warnings=row.get("warnings") or [],
        options=row.get("options") or {},
        documents=[
            AgentApplicationDocument(
                kind=doc["kind"],
                version=int(doc["version"]),
                origin=doc["origin"],
                notes=doc.get("notes") or [],
                content=doc.get("content") or "",
            )
            for doc in (row.get("documents") or [])
        ],
        result=row.get("result"),
    )


def _get(conn, application_id: UUID, user_id: UUID) -> dict:
    row = store.detail_for_user(conn, application_id, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return row


def _state_error(exc: store.InvalidState) -> HTTPException:
    return HTTPException(status_code=409, detail=str(exc))


def _join(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


@router.post("", response_model=StartResult, status_code=202)
def start(body: StartRequest, conn: ConnectionDep) -> StartResult:
    # Auto-apply tailors documents and reads forms with Gemini. Asking for the
    # key here is clearer than queueing a run that will fail minutes later.
    try:
        ai_keys.require_key(
            conn,
            body.user_id,
            "Add your Gemini API key in Settings before starting an "
            "application.",
        )
    except ai_keys.MissingApiKey as exc:
        raise HTTPException(status_code=428, detail=str(exc)) from exc

    missing = store.missing_setup(conn, body.user_id)
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Before applying, add "
            + _join(missing)
            + " in your profile.",
        )
    try:
        batch_id, jobs, skipped = enqueue(
            conn,
            user_id=body.user_id,
            job_ids=body.job_ids,
        )
    except JobsNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return StartResult(
        batchId=batch_id,
        count=len(jobs),
        jobs=[AgentApplicationItem(**job) for job in jobs],
        skipped=skipped,
    )


@router.get("", response_model=list[AgentApplicationSummary])
def list_applications(
    user_id: UUID,
    conn: ConnectionDep,
    limit: int = 50,
) -> list[AgentApplicationSummary]:
    return [
        _summary(row)
        for row in store.list_for_user(
            conn, user_id, max(1, min(limit, 100))
        )
    ]


@router.get("/{application_id}", response_model=AgentApplicationDetail)
def get_application(
    application_id: UUID,
    user_id: UUID,
    conn: ConnectionDep,
) -> AgentApplicationDetail:
    return _detail(_get(conn, application_id, user_id))


@router.get("/{application_id}/documents/{kind}/pdf")
def get_document_pdf(
    application_id: UUID,
    kind: str,
    user_id: UUID,
    conn: ConnectionDep,
    version: int | None = None,
) -> Response:
    """The exact PDF that was uploaded to the employer, when there is one.

    A CV tailored from the candidate's own DOCX is rendered once at generation
    time. Re-rendering its plain text in the browser loses the layout, so the
    stored file is served instead. Documents without one (cover letters,
    hand-edited versions) fall back to the printable text in the UI.
    """
    if kind not in {"cv", "cover_letter"}:
        raise HTTPException(status_code=404, detail="Document not found.")
    found = store.document_pdf(conn, application_id, user_id, kind, version)
    if found is None:
        raise HTTPException(
            status_code=404, detail="This document has no stored PDF."
        )
    number, data = found
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{kind}-v{number}.pdf"'
            )
        },
    )


@router.post(
    "/{application_id}/answers",
    response_model=AnswerResult,
)
def answer_questions(
    application_id: UUID,
    user_id: UUID,
    body: AnswerRequest,
    conn: ConnectionDep,
) -> AnswerResult:
    try:
        answered = store.answer(
            conn,
            application_id,
            user_id,
            body.answers,
        )
    except store.NotFound as exc:
        raise HTTPException(
            status_code=404, detail="Application not found."
        ) from exc
    except store.InvalidState as exc:
        raise _state_error(exc) from exc
    return AnswerResult(
        id=application_id,
        status="queued",
        answered=answered,
    )


@router.post(
    "/{application_id}/approve",
    response_model=AgentApplicationDetail,
)
def approve(
    application_id: UUID,
    user_id: UUID,
    conn: ConnectionDep,
) -> AgentApplicationDetail:
    try:
        store.approve(conn, application_id, user_id)
    except store.NotFound as exc:
        raise HTTPException(
            status_code=404, detail="Application not found."
        ) from exc
    except store.InvalidState as exc:
        raise _state_error(exc) from exc
    return _detail(_get(conn, application_id, user_id))


@router.post(
    "/{application_id}/retry",
    response_model=AgentApplicationDetail,
)
def retry(
    application_id: UUID,
    user_id: UUID,
    conn: ConnectionDep,
) -> AgentApplicationDetail:
    try:
        store.retry(conn, application_id, user_id)
    except store.NotFound as exc:
        raise HTTPException(
            status_code=404, detail="Application not found."
        ) from exc
    except store.InvalidState as exc:
        raise _state_error(exc) from exc
    return _detail(_get(conn, application_id, user_id))


@router.post(
    "/{application_id}/cancel",
    response_model=AgentApplicationDetail,
)
def cancel(
    application_id: UUID,
    user_id: UUID,
    conn: ConnectionDep,
) -> AgentApplicationDetail:
    try:
        store.cancel(conn, application_id, user_id)
    except store.NotFound as exc:
        raise HTTPException(
            status_code=404, detail="Application not found."
        ) from exc
    except store.InvalidState as exc:
        raise _state_error(exc) from exc
    return _detail(_get(conn, application_id, user_id))
