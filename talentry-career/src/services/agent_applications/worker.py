"""Standalone worker process for auto-apply jobs."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import psycopg

from config.settings import get_database_url, settings
from db.schema import ensure_schema
from services.browser import BrowserSession

from . import store
from .agent import (
    Agent,
    ActionError,
    FormChanged,
    NeedsManual,
    StaleApproval,
)

log = logging.getLogger("talentry.agent")

# Plain-language reasons a run can stop. The technical text stays in the logs
# and in the Activity list; the user gets one sentence they can act on.
_PLAIN_REASONS: list[tuple[str, str]] = [
    (
        r"captcha|not a robot|prove (that )?you are (a )?human",
        "The employer's page asked for a CAPTCHA, which Talentry cannot solve. "
        "Finish this application on their site, or try again later.",
    ),
    (
        r"sign in|sign-in|log in|login|password|create an account",
        "This application needs an account or a sign-in on the employer's site.",
    ),
    (
        r"timed out|timeout|deadline exceeded",
        "The employer's site stopped responding.",
    ),
    (
        r"net::|err_|connection (refused|reset)|could not be reached|"
        r"name or service not known|dns",
        "Talentry could not reach the employer's site.",
    ),
    (
        r"page (did not|no longer)|no form|application form|"
        r"could not (open|load)|404",
        "The application page could not be opened.",
    ),
    (
        r"form changed|no longer match",
        "The form changed while Talentry was filling it, so the answers no "
        "longer matched.",
    ),
]


def explain(exc: Exception) -> str:
    """One sentence for the user: why this run could not continue."""
    text = str(exc).strip()
    for pattern, reason in _PLAIN_REASONS:
        if re.search(pattern, text.lower()):
            return reason
    # Messages written for the user already (e.g. "The employer site blocked
    # automated access.") are kept as they are.
    if (
        text
        and len(text) <= 240
        and text[0].isupper()
        and text.endswith((".", "!", "?"))
    ):
        return text
    return "Something went wrong while Talentry was filling in the form."


class Worker:
    def __init__(self) -> None:
        self.stop = asyncio.Event()

    async def run(self) -> None:
        while not self.stop.is_set():
            conn: psycopg.Connection | None = None
            try:
                conn = psycopg.connect(
                    get_database_url(), autocommit=True
                )
                ensure_schema(conn)
                while not self.stop.is_set():
                    store.recover_stale(
                        conn, settings.AGENT_STALE_MINUTES
                    )
                    application = store.claim_next(conn)
                    if application is None:
                        await self.sleep(settings.AGENT_POLL_SECONDS)
                        continue
                    await self.process(conn, application)
            except psycopg.Error:
                log.exception("Database connection failed; retrying.")
                await self.sleep(5)
            finally:
                if conn is not None:
                    conn.close()

    async def sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def notify(
        self,
        conn: psycopg.Connection,
        application: dict[str, Any],
        outcome: str,
        body: str | None = None,
    ) -> None:
        messages = {
            "needs_input": (
                "Application needs your input",
                "Answer the questions to continue.",
            ),
            "pending_approval": (
                "Application ready for review",
                "Check the answers and documents before submitting.",
            ),
            "submitted": (
                "Application submitted",
                "The employer confirmed your application.",
            ),
            "unconfirmed": (
                "Check your application",
                "The application was sent, but it could not be confirmed.",
            ),
            "failed": (
                "Application could not be completed",
                "Open the application to see why and try again.",
            ),
        }
        title, default_body = messages.get(
            outcome,
            ("Application needs attention", "Open the application to review it."),
        )
        try:
            store.notify(
                conn,
                application,
                outcome,
                title,
                body or default_body,
            )
        except psycopg.Error:
            log.exception("Could not create notification.")

    async def process(
        self,
        conn: psycopg.Connection,
        application: dict[str, Any],
    ) -> None:
        agent: Agent | None = None
        application_id = application["id"]
        status = application["status"]
        try:
            async with BrowserSession(
                storage_state=application.get("browser_state")
            ) as session:
                agent = Agent(conn, application, session)
                url = application.get("apply_url") or agent.job.get("url")
                if not url:
                    raise NeedsManual(
                        "This job has no application URL."
                    )
                if status == "submitting":
                    outcome = await agent.submit(url)
                else:
                    outcome = await agent.prepare(url)
                self.notify(conn, application, outcome)
        except NeedsManual as exc:
            await self.manual(conn, agent, application, str(exc))
        except StaleApproval as exc:
            await self.review(
                conn,
                agent,
                application,
                f"Please review this application again: {exc}",
            )
        except FormChanged as exc:
            await self.review(
                conn,
                agent,
                application,
                f"The form changed before submission: {exc}",
            )
        except store.Cancelled:
            log.info("Application %s was changed by the user.", application_id)
        except ActionError as exc:
            await self.failed(conn, agent, application, exc)
        except Exception as exc:
            log.exception("Application %s failed.", application_id)
            await self.failed(conn, agent, application, exc)

    async def manual(
        self,
        conn: psycopg.Connection,
        agent: Agent | None,
        application: dict[str, Any],
        message: str,
    ) -> None:
        if agent is not None and agent.clicked_submit:
            await self.unconfirmed(conn, application, message)
            return
        target = (
            "pending_approval"
            if application["status"] == "submitting"
            else "needs_input"
        )
        if agent is None:
            store.finish(
                conn,
                application["id"],
                target,
                approved_snapshot=None,
                approved_at=None,
                error=message,
            )
            self.notify(conn, application, target)
            return
        agent.manual(message, "The agent cannot continue automatically.")
        try:
            agent.checkpoint()
            store.finish(
                conn,
                application["id"],
                target,
                approved_snapshot=None,
                approved_at=None,
                error=message,
            )
            agent.log("manual", message)
        except store.Cancelled:
            return
        self.notify(conn, application, target)

    async def review(
        self,
        conn: psycopg.Connection,
        agent: Agent | None,
        application: dict[str, Any],
        message: str,
    ) -> None:
        if agent is not None and agent.clicked_submit:
            await self.unconfirmed(conn, application, message)
            return
        if agent is not None:
            agent.manual(message, "The approved details no longer match.")
            try:
                agent.checkpoint()
            except store.Cancelled:
                return
        try:
            store.finish(
                conn,
                application["id"],
                "pending_approval",
                approved_snapshot=None,
                approved_at=None,
                error=message,
            )
            store.event(
                conn,
                application["id"],
                "review",
                message,
            )
        except store.Cancelled:
            return
        self.notify(conn, application, "pending_approval")

    async def unconfirmed(
        self,
        conn: psycopg.Connection,
        application: dict[str, Any],
        message: str,
    ) -> None:
        try:
            store.finish(
                conn,
                application["id"],
                "unconfirmed",
                error=message,
            )
        except store.Cancelled:
            return
        store.event(
            conn,
            application["id"],
            "unconfirmed",
            message,
        )
        self.notify(conn, application, "unconfirmed")

    async def failed(
        self,
        conn: psycopg.Connection,
        agent: Agent | None,
        application: dict[str, Any],
        exc: Exception,
    ) -> None:
        if agent is not None and agent.clicked_submit:
            await self.unconfirmed(conn, application, explain(exc))
            return
        reason = explain(exc)
        attempts = int(application.get("attempts") or 0)
        if attempts + 1 < settings.AGENT_MAX_ATTEMPTS:
            try:
                retry_status = (
                    "approved"
                    if application["status"] == "submitting"
                    else "queued"
                )
                store.requeue(
                    conn,
                    application["id"],
                    retry_status,
                    min(60, 5 * (attempts + 1)),
                    reason,
                )
                store.event(
                    conn,
                    application["id"],
                    "retry",
                    f"Attempt {attempts + 1} failed: {reason}",
                )
            except store.Cancelled:
                return
            return
        try:
            store.finish(
                conn,
                application["id"],
                "failed",
                error=reason,
            )
            store.event(
                conn,
                application["id"],
                "failed",
                reason,
            )
        except store.Cancelled:
            return
        self.notify(conn, application, "failed", reason)


async def main() -> None:
    worker = Worker()
    try:
        await worker.run()
    except KeyboardInterrupt:
        worker.stop.set()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(main())
