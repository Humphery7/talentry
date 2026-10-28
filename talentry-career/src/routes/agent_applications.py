from uuid import UUID

from fastapi import APIRouter, HTTPException

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


@router.post("", response_model=StartResult, status_code=202)
def start(body: StartRequest, conn: ConnectionDep) -> StartResult:
    try:
        batch_id, jobs = enqueue(
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
