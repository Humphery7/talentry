"""Errors raised by the browser tools."""


class ToolError(RuntimeError):
    """A browser action could not be completed."""


class SubmitBlocked(ToolError):
    """A click was refused because it looked like an application submit."""
