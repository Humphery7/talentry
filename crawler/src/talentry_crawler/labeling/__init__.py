"""Turn a raw job into a labeled one (seniority, occupation, technologies). Pure logic, no I/O."""

from .labeler import Labeler

__all__ = ["Labeler"]
