"""Browser lifecycle for the auto-apply agent."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from config.settings import settings

from .safety import SUBMIT_GUARD_SCRIPT
from .tools import PageTools


class BrowserSession:
    """One browser, one context, and one page for an application run."""

    def __init__(
        self,
        *,
        headless: bool | None = None,
        channel: str | None = None,
        timeout_ms: int | None = None,
        slow_mo_ms: int | None = None,
        storage_state: str | Path | dict[str, Any] | None = None,
    ) -> None:
        self.headless = (
            settings.PLAYWRIGHT_HEADLESS if headless is None else headless
        )
        resolved_channel = (
            channel if channel is not None else settings.PLAYWRIGHT_CHANNEL
        )
        self.channel = (resolved_channel or "").strip() or None
        self.timeout_ms = (
            settings.PLAYWRIGHT_TIMEOUT_MS if timeout_ms is None else timeout_ms
        )
        self.slow_mo_ms = (
            settings.PLAYWRIGHT_SLOW_MO_MS if slow_mo_ms is None else slow_mo_ms
        )
        self.storage_state = (
            str(storage_state)
            if isinstance(storage_state, Path)
            else storage_state
        )
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._tools: PageTools | None = None

    async def start(self) -> None:
        if self._page is not None and not self._page.is_closed():
            return
        if self._playwright is not None:
            await self.close()
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                channel=self.channel,
                slow_mo=self.slow_mo_ms,
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                storage_state=self.storage_state,
            )
            await self._context.add_init_script(SUBMIT_GUARD_SCRIPT)
            self._context.set_default_timeout(self.timeout_ms)
            self._context.set_default_navigation_timeout(self.timeout_ms)
            self._page = await self._context.new_page()
            self._page.set_default_timeout(self.timeout_ms)
            self._page.set_default_navigation_timeout(self.timeout_ms)
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        page = self._page
        context = self._context
        browser = self._browser
        playwright = self._playwright
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._tools = None
        if page is not None and not page.is_closed():
            with suppress(Exception):
                await page.close()
        if context is not None:
            with suppress(Exception):
                await context.close()
        if browser is not None:
            with suppress(Exception):
                await browser.close()
        if playwright is not None:
            with suppress(Exception):
                await playwright.stop()

    async def __aenter__(self) -> BrowserSession:
        await self.start()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser session has not started.")
        return self._page

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("Browser session has not started.")
        return self._context

    @property
    def tools(self) -> PageTools:
        if self._tools is None:
            self._tools = PageTools(self.page, timeout_ms=self.timeout_ms)
        return self._tools

    async def new_page(self) -> Page:
        return await self.context.new_page()

    async def screenshot_jpeg(self) -> bytes:
        return await self.page.screenshot(
            type="jpeg",
            quality=55,
            full_page=True,
        )

    async def render_pdf(self, html: str, path: str | Path) -> None:
        page = await self.context.new_page()
        try:
            await page.set_content(html)
            await page.pdf(
                path=str(path),
                format="A4",
                margin={
                    "top": "18mm",
                    "bottom": "18mm",
                    "left": "16mm",
                    "right": "16mm",
                },
            )
        finally:
            await page.close()

    async def save_storage_state(
        self,
        path: str | Path | None = None,
    ) -> dict[str, Any]:
        return await self.context.storage_state(
            path=str(path) if path is not None else None
        )
