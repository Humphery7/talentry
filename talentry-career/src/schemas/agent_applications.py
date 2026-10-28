"""Request, response, and stored-plan models for agent applications."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

JobId = Annotated[int, Field(ge=1)]


class AgentApplicationStatus(str, Enum):
    queued = "queued"
    in_progress = "in_progress"
    needs_input = "needs_input"
    pending_approval = "pending_approval"
    approved = "approved"
    submitting = "submitting"
    submitted = "submitted"
    unconfirmed = "unconfirmed"
    failed = "failed"
    cancelled = "cancelled"


class StartRequest(BaseModel):
    user_id: UUID
    job_ids: list[JobId] = Field(min_length=1, max_length=50)


class AgentApplicationItem(BaseModel):
    jobId: int
    status: str


class StartResult(BaseModel):
    batchId: UUID
    count: int
    jobs: list[AgentApplicationItem]


class AttentionItem(BaseModel):
    id: str
    kind: Literal["question", "manual"]
    field_key: str | None = None
    question: str
    why: str | None = None
    context: str | None = None
    options: list[str] | None = None
    sensitive: bool = False
    category: str | None = None
    fact_key: str | None = None
    answer: str | None = None


class PlanField(BaseModel):
    label: str
    kind: str
    required: bool
    value: str
    source: str
    status: str
    options: list[str] | None = None
    doc: str | None = None
    pos: int = 0
    sensitive: bool = False
    note: str | None = None


class ApplicationPlan(BaseModel):
    fields: dict[str, PlanField] = Field(default_factory=dict)


class AgentApplicationDocument(BaseModel):
    kind: str
    version: int
    origin: str
    notes: list[str] = Field(default_factory=list)
    content: str = ""


class AgentApplicationSummary(BaseModel):
    id: UUID
    batchId: UUID
    jobId: int
    status: str
    platform: str | None = None
    applyUrl: str | None = None
    jobTitle: str | None = None
    company: str | None = None
    error: str | None = None
    warningCount: int = 0
    attentionCount: int = 0
    createdAt: datetime
    updatedAt: datetime
    approvedAt: datetime | None = None
    submittedAt: datetime | None = None
    screenshot: str | None = None


class AgentApplicationDetail(AgentApplicationSummary):
    plan: dict = Field(default_factory=dict)
    attention: list[AttentionItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    options: dict = Field(default_factory=dict)
    documents: list[AgentApplicationDocument] = Field(default_factory=list)
    result: dict | None = None


class AnswerRequest(BaseModel):
    answers: dict[str, str] = Field(min_length=1)


class AnswerResult(BaseModel):
    id: UUID
    status: str
    answered: int
