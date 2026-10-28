"""Reusable browser automation for the auto-apply agent."""

from schemas.browser import (
    ActionResult,
    ElementInfo,
    FrameInfo,
    OptionInfo,
    PageInspection,
    PageSignals,
)

from .errors import SubmitBlocked, ToolError
from .session import BrowserSession
from .tools import PageTools

__all__ = [
    "ActionResult",
    "BrowserSession",
    "ElementInfo",
    "FrameInfo",
    "OptionInfo",
    "PageInspection",
    "PageSignals",
    "PageTools",
    "SubmitBlocked",
    "ToolError",
]
