"""Talk to external ATS APIs. One file per provider. No database writes here."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx

from talentry_crawler.models import Board, Job

from . import ashby, greenhouse, lever

DiscoverFn = Callable[[Board, httpx.AsyncClient], Awaitable[list[Job]]]

# Register every supported provider here. Adding Workday later = new file + one line.
REGISTRY: dict[str, DiscoverFn] = {
    "greenhouse": greenhouse.discover,
    "ashby": ashby.discover,
    "lever": lever.discover,
}


def get_discoverer(monitor_type: str) -> DiscoverFn:
    try:
        return REGISTRY[monitor_type]
    except KeyError as exc:
        raise KeyError(
            f"No ATS adapter for {monitor_type!r}. Available: {sorted(REGISTRY)}"
        ) from exc
