"""Internal models for the form-filling agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from schemas.browser import PageSignals


class FormOption(BaseModel):
    element_id: str | None = None
    value: str = ""
    label: str


class FormField(BaseModel):
    element_id: str
    key: str
    label: str
    kind: str
    action: Literal[
        "fill",
        "select",
        "combobox",
        "radio",
        "checkbox",
        "upload",
        "click",
    ]
    required: bool = False
    value: str = ""
    options: list[FormOption] = Field(default_factory=list)
    pos: int = 0
    section: str | None = None
    maxlength: int | None = None
    sensitive: bool = False


class FormButton(BaseModel):
    element_id: str
    text: str
    kind: Literal["button", "link"]
    is_submit: bool = False


class FormObservation(BaseModel):
    url: str
    title: str
    text: str
    fields: list[FormField] = Field(default_factory=list)
    buttons: list[FormButton] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    signals: PageSignals = Field(default_factory=PageSignals)


class AgentAction(BaseModel):
    type: Literal["set", "ask", "skip", "click"]
    element_id: str
    source: Literal["profile", "document", "draft"] | None = None
    key: str | None = None
    text: str | None = None
    question: str | None = None
    why: str | None = None


class AgentDecision(BaseModel):
    actions: list[AgentAction] = Field(default_factory=list)
