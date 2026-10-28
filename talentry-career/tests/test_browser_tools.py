import asyncio
import os
import sys
from pathlib import Path

import pytest
from playwright.async_api import Error as PlaywrightError

from services.agent_applications.form import build_observation
from services.browser import BrowserSession, ElementInfo, PageInspection

CHANNEL = os.getenv("PLAYWRIGHT_CHANNEL") or (
    "chrome" if sys.platform == "darwin" else None
)

HTML = """
<!doctype html>
<html>
  <head><title>Application</title></head>
  <body>
    <h1>Apply</h1>
    <form>
      <label for="name">Full name</label>
      <input id="name" name="name" placeholder="Your name" required>
      <label for="email">Email</label>
      <input id="email" type="email" name="email">
      <label for="company">Company</label>
      <input id="company" role="combobox" name="company" aria-expanded="false">
      <div id="custom-select" role="combobox" aria-expanded="false" tabindex="0">
        Choose an option
      </div>
      <label for="country">Country</label>
      <select id="country" name="country">
        <option value="">Choose a country</option>
        <option value="us">United States</option>
        <option value="ca">Canada</option>
      </select>
      <label><input id="remote" type="checkbox" name="remote"> Remote</label>
      <label id="newsletter-label">
        <input id="newsletter" type="checkbox" name="newsletter"
          style="display:none"> Newsletter
      </label>
      <div id="custom-check" role="checkbox" aria-checked="false" tabindex="0"
        onclick="this.setAttribute('aria-checked',
          this.getAttribute('aria-checked') === 'true' ? 'false' : 'true')">
        Custom option
      </div>
      <label for="cv">CV</label>
      <input id="cv" type="file" name="cv" accept=".pdf">
      <input id="hidden-cv" type="file" name="hidden_cv" style="display:none">
      <button id="click-me" type="button"
        onclick="document.getElementById('status').textContent='clicked'">
        Click me
      </button>
      <p id="status"></p>
    </form>
    <a href="https://example.com" id="site">Company site</a>
    <div id="shadow-host"></div>
    <iframe srcdoc="<label>Frame field <input name='frame'></label>"></iframe>
    <script>
      const host = document.getElementById('shadow-host');
      const root = host.attachShadow({ mode: 'open' });
      root.innerHTML = '<label>Shadow field <input name="shadow"></label>';
    </script>
  </body>
</html>
"""


def find(inspection: PageInspection, **matches: object) -> ElementInfo:
    for element in inspection.elements:
        if all(getattr(element, key) == value for key, value in matches.items()):
            return element
    raise AssertionError(f"No element matched {matches}")


async def _exercise(tmp_path: Path) -> None:
    session = BrowserSession(headless=True, channel=CHANNEL)
    try:
        await session.start()
    except PlaywrightError as exc:
        message = str(exc)
        if (
            "Executable doesn't exist" in message
            or "does not support" in message
            or "missing dependencies" in message
            or "is not found" in message
        ):
            pytest.skip(f"Playwright browser unavailable: {message}")
        raise

    try:
        page = session.page
        await page.set_content(HTML)
        await page.wait_for_timeout(100)
        tools = session.tools

        inspection = await tools.inspect_page()
        assert inspection.title == "Application"
        assert inspection.ready_state in {"interactive", "complete"}
        assert "Apply" in inspection.text
        ids = [element.id for element in inspection.elements]
        assert len(ids) == len(set(ids))

        observation = build_observation(inspection)
        by_label = {field.label: field for field in observation.fields}
        assert by_label["Full name"].action == "fill"
        assert by_label["Company"].action == "combobox"
        assert by_label["Country"].action == "select"
        assert by_label["Remote"].action == "checkbox"
        assert by_label["Newsletter"].action == "click"
        assert by_label["Custom option"].action == "click"
        assert by_label["CV"].action == "upload"
        assert by_label["Shadow field"].action == "fill"
        assert by_label["Frame field"].action == "fill"
        assert [button.text for button in observation.buttons] == [
            "Click me",
            "Company site",
        ]

        name = find(inspection, name="name")
        assert name.label == "Full name"
        assert name.type == "text"
        assert name.required is True

        email = find(inspection, name="email")
        assert email.type == "email"

        company = find(inspection, name="company")
        assert company.role == "combobox"

        custom_select = find(
            inspection,
            role="combobox",
            text="Choose an option",
        )

        country = find(inspection, name="country")
        assert country.tag == "select"
        assert [option.label for option in country.options or []] == [
            "Choose a country",
            "United States",
            "Canada",
        ]

        remote = find(inspection, name="remote")
        assert remote.type == "checkbox"
        assert remote.label == "Remote"

        cv = find(inspection, name="cv")
        assert cv.type == "file"
        assert cv.accept == ".pdf"

        button = find(inspection, text="Click me")
        link = find(inspection, text="Company site")
        assert link.href == "https://example.com/"

        shadow = find(inspection, name="shadow")
        assert shadow.label == "Shadow field"
        assert shadow.frame_index == 0

        frame_field = find(inspection, name="frame")
        assert frame_field.label == "Frame field"
        frame = next(frame for frame in page.frames if frame != page.main_frame)
        assert frame_field.frame_index == page.frames.index(frame)
        assert any(
            item.index == frame_field.frame_index and not item.is_main
            for item in inspection.frames
        )

        result = await tools.fill_field(name.id, "Ada Lovelace")
        assert result.ok, result.message
        assert await page.locator("#name").input_value() == "Ada Lovelace"

        result = await tools.fill_field(company.id, "Acme")
        assert result.ok, result.message
        assert await page.locator("#company").input_value() == "Acme"

        result = await tools.press_key(name.id, "Tab")
        assert result.ok, result.message
        assert await page.evaluate("document.activeElement.name") == "email"

        result = await tools.select_option(country.id, "Canada")
        assert result.ok, result.message
        assert await page.locator("#country").input_value() == "ca"

        result = await tools.set_checked(remote.id, True)
        assert result.ok, result.message
        assert await page.locator("#remote").is_checked()

        result = await tools.set_checked(remote.id, False)
        assert result.ok, result.message
        assert not await page.locator("#remote").is_checked()

        newsletter_label = find(inspection, tag="label", label="Newsletter")
        assert newsletter_label.visible is True
        assert newsletter_label.type == "checkbox"
        assert newsletter_label.checked is False
        result = await tools.click_element(newsletter_label.id)
        assert result.ok, result.message
        assert await page.locator("#newsletter").is_checked()

        custom = find(inspection, role="checkbox", text="Custom option")
        assert custom.checked is False
        result = await tools.click_element(custom.id)
        assert result.ok, result.message
        assert (
            await page.locator("#custom-check").get_attribute("aria-checked")
            == "true"
        )

        cv_file = tmp_path / "cv.pdf"
        cv_file.write_bytes(b"%PDF-1.4 test")
        result = await tools.upload_file(cv.id, cv_file)
        assert result.ok, result.message
        assert await page.locator("#cv").evaluate("el => el.files.length") == 1

        hidden_cv = find(inspection, name="hidden_cv")
        assert hidden_cv.visible is False
        result = await tools.upload_file(hidden_cv.id, cv_file)
        assert result.ok, result.message
        assert (
            await page.locator("#hidden-cv").evaluate("el => el.files.length") == 1
        )

        result = await tools.fill_field(shadow.id, "shadow value")
        assert result.ok, result.message
        assert (
            await page.locator("#shadow-host").evaluate(
                "el => el.shadowRoot.querySelector('input').value"
            )
            == "shadow value"
        )

        result = await tools.fill_field(frame_field.id, "frame value")
        assert result.ok, result.message
        assert await frame.locator("input[name=frame]").input_value() == "frame value"

        result = await tools.click_element(button.id)
        assert result.ok, result.message
        assert await page.locator("#status").inner_text() == "clicked"

        result = await tools.fill_field(custom_select.id, "Acme")
        assert not result.ok
        assert "custom dropdown" in result.message

        result = await tools.fill_field("missing", "value")
        assert not result.ok
        assert "Unknown element id" in result.message

        result = await tools.navigate("file:///tmp/nope")
        assert not result.ok
        assert "http and https" in result.message

        state = await session.save_storage_state()
        assert "cookies" in state

        again = await tools.inspect_page()
        assert find(again, name="name").id == name.id
        assert find(again, tag="label", label="Newsletter").checked is True
        assert find(again, role="checkbox", text="Custom option").checked is True
    finally:
        await session.close()


def test_browser_tools(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))
