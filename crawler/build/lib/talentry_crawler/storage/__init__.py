"""Persist jobs. Swap sqlite → postgres later without touching ats/."""

from .sqlite import JobStore

__all__ = ["JobStore"]
