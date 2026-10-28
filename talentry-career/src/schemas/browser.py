"""Data returned by the browser tools.

These are internal value objects, not request/response bodies. They live in
`schemas` so every data shape in the service follows the same rule: schemas
describe data, services contain behaviour.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OptionInfo(BaseModel):
    value: str
    label: str
    disabled: bool = False


class ElementInfo(BaseModel):
    id: str
    tag: str
    type: str | None = None
    role: str | None = None
    label: str | None = None
    name: str | None = None
    placeholder: str | None = None
    text: str | None = None
    value: str | None = None
    href: str | None = None
    autocomplete: str | None = None
    accept: str | None = None
    required: bool = False
    disabled: bool = False
    read_only: bool = False
    checked: bool | None = None
    multiple: bool | None = None
    visible: bool = True
    editable: bool = False
    has_value: bool = False
    options: list[OptionInfo] | None = None
    options_truncated: bool = False
    section: str | None = None
    maxlength: int | None = None
    frame_index: int = 0


class FrameInfo(BaseModel):
    index: int
    name: str | None
    url: str
    is_main: bool
    text: str
    text_truncated: bool = False


class PageSignals(BaseModel):
    captcha: bool = False
    login: bool = False
    text_fields: int = 0
    has_file: bool = False
    confirmation: bool = False
    bot_block: bool = False


class PageInspection(BaseModel):
    url: str
    title: str
    text: str
    ready_state: str
    elements: list[ElementInfo] = Field(default_factory=list)
    frames: list[FrameInfo] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    signals: PageSignals = Field(default_factory=PageSignals)
    elements_truncated: bool = False
    text_truncated: bool = False


class ActionResult(BaseModel):
    ok: bool
    message: str
    element_id: str | None = None
    url: str | None = None
    title: str | None = None
