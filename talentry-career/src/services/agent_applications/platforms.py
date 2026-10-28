"""Where each supported ATS keeps its application form."""

from __future__ import annotations

from urllib.parse import urlparse


def detect(monitor_type: str | None, url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if monitor_type in ("greenhouse", "lever", "ashby"):
        return monitor_type
    for name, needle in (
        ("greenhouse", "greenhouse.io"),
        ("lever", "lever.co"),
        ("ashby", "ashbyhq.com"),
    ):
        if needle in host:
            return name
    return "generic"


def apply_url(platform: str, job_url: str) -> str:
    base = job_url.split("?")[0].rstrip("/")
    if platform == "lever" and not base.endswith("/apply"):
        return base + "/apply"
    if platform == "ashby" and not base.endswith("/application"):
        return base + "/application"
    return job_url
