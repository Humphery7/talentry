"""Auto-apply workflow: queueing, form decisions, and the background worker."""

from .queue import JobsNotFound, enqueue

__all__ = ["JobsNotFound", "enqueue"]
