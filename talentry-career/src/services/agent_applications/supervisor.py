"""Keeps the auto-apply worker running next to the API.

The worker is normally its own process (``python -m
services.agent_applications.worker``). When that is not practical — for example
a deployment that only starts the FastAPI app — this supervisor launches it as
a child process and restarts it if it exits. Set ``AGENT_WORKER_ENABLED=0`` to
turn it off (the local ``npm run dev`` script does this because it starts the
worker separately).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("talentry.agent.supervisor")

# .../talentry-career/src/services/agent_applications/supervisor.py
ROOT = Path(__file__).resolve().parents[3]

_FALSE = {"0", "false", "no", "off"}


def _enabled() -> bool:
    return os.getenv("AGENT_WORKER_ENABLED", "1").strip().lower() not in _FALSE


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    src = str(ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src}{os.pathsep}{existing}" if existing else src
    return env


class WorkerSupervisor:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._process: asyncio.subprocess.Process | None = None

    def start(self) -> None:
        if not _enabled():
            log.info("Auto-apply worker disabled (AGENT_WORKER_ENABLED).")
            return
        self._task = asyncio.create_task(
            self._run(), name="agent-worker-supervisor"
        )

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "services.agent_applications.worker",
                    cwd=str(ROOT),
                    env=_environment(),
                )
                log.info(
                    "Auto-apply worker started (pid %s).",
                    self._process.pid,
                )
                code = await self._process.wait()
                if self._stop.is_set():
                    break
                log.warning(
                    "Auto-apply worker exited with code %s; restarting.",
                    code,
                )
            except Exception:
                log.exception(
                    "Could not start auto-apply worker; retrying in 5s."
                )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=10)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
