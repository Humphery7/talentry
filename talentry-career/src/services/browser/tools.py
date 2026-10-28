"""Generic Playwright actions for the auto-apply agent."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Locator, Page

from schemas.browser import (
    ActionResult,
    ElementInfo,
    FrameInfo,
    OptionInfo,
    PageInspection,
    PageSignals,
)

from .errors import SubmitBlocked, ToolError
from .safety import BOT_RE, CONFIRM_RE, NEXT_RE, SUBMIT_RE

logger = logging.getLogger(__name__)

MAX_ELEMENTS_PER_FRAME = 200
MAX_ELEMENTS = 400
MAX_OPTIONS = 100
MAX_TEXT = 8_000
MAX_FRAME_TEXT = 4_000

INSPECT_JS = r"""
(arg) => {
  const maxElements = arg.maxElements;
  const maxText = arg.maxText;
  const frameIndex = arg.frameIndex;
  const token = arg.token;
  const prefix = `talentry-${token}-f${frameIndex}-`;
  const idPattern = new RegExp(`^talentry-${token}-f${frameIndex}-\\d+$`);
  const confirmationRe = /thank you for (applying|your application|your interest)|application (has been |was )?(submitted|received|sent)|we(’|')?ve received your application|successfully submitted|your application is (in|complete)/i;
  const botRe = /verify you are (a )?human|unusual traffic|checking your browser|access denied|just a moment/i;
  const interactiveSelector = [
    'a[href]',
    'button',
    'input',
    'label',
    'textarea',
    'select',
    'summary',
    '[contenteditable]:not([contenteditable="false"])',
    '[role="button"]',
    '[role="link"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="switch"]',
    '[role="combobox"]',
    '[role="textbox"]',
    '[role="searchbox"]',
    '[role="spinbutton"]',
    '[role="slider"]',
    '[role="tab"]',
    '[role="menuitem"]',
    '[role="menuitemcheckbox"]',
    '[role="menuitemradio"]',
    '[role="option"]',
    '[role="treeitem"]',
  ].join(',');
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const pageText = (value) => (value || '')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  const textOf = (el) => clean(el.innerText || el.textContent || '');
  const isVisible = (el) => {
    if (el.getAttribute('aria-hidden') === 'true') return false;
    if (el.closest('[inert]')) return false;
    if (typeof el.checkVisibility === 'function') {
      return el.checkVisibility({ checkVisibilityCSS: true });
    }
    const style = window.getComputedStyle(el);
    if (
      style.display === 'none' ||
      style.visibility === 'hidden' ||
      style.visibility === 'collapse'
    ) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const labelOf = (el) => {
    const labels = el.labels
      ? Array.from(el.labels).map(textOf).filter(Boolean)
      : [];
    if (labels.length) return labels.join(' ');
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) return clean(ariaLabel);
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const root = el.getRootNode();
      const parts = labelledBy
        .split(/\s+/)
        .map((id) => (
          root.getElementById ? root.getElementById(id) : document.getElementById(id)
        ))
        .filter(Boolean)
        .map(textOf);
      if (parts.length) return parts.join(' ');
    }
    const parentLabel = el.closest('label');
    if (parentLabel) return textOf(parentLabel);
    const fieldset = el.closest('fieldset');
    if (fieldset) {
      const legend = fieldset.querySelector('legend');
      if (legend) return textOf(legend);
    }
    return '';
  };
  const sectionOf = (el) => {
    const fieldset = el.closest('fieldset');
    if (fieldset) {
      const legend = fieldset.querySelector('legend');
      if (legend) return textOf(legend);
    }
    let node = el;
    while (node && node !== document.body) {
      let previous = node.previousElementSibling;
      while (previous) {
        if (/^H[1-4]$/.test(previous.tagName)) return textOf(previous);
        previous = previous.previousElementSibling;
      }
      node = node.parentElement;
    }
    return '';
  };
  const seen = new Set();
  const elements = [];
  let truncated = false;
  let counter = window.__talentryIdCounter || 0;
  const collect = (root) => {
    const nodes = root.querySelectorAll('*');
    for (const el of nodes) {
      if (elements.length >= maxElements) {
        truncated = true;
        return;
      }
      if (el.shadowRoot) collect(el.shadowRoot);
      if (!el.matches(interactiveSelector)) continue;
      if (seen.has(el)) continue;
      seen.add(el);
      const tag = el.tagName.toLowerCase();
      const type = (tag === 'input' || tag === 'button')
        ? (el.type || '').toLowerCase()
        : (el.getAttribute('type') || '').toLowerCase();
      if (tag === 'input' && type === 'hidden') continue;
      let labelControl = null;
      if (tag === 'label') {
        const role = (el.getAttribute('role') || '').toLowerCase();
        const plainLabel = !role ||
          role === 'label' ||
          role === 'presentation' ||
          role === 'none';
        if (plainLabel) {
          labelControl = el.control || el.querySelector(
            'input[type="checkbox"], input[type="radio"]'
          );
          const controlType = (
            labelControl && labelControl.type || ''
          ).toLowerCase();
          if (controlType !== 'checkbox' && controlType !== 'radio') continue;
        }
      }
      const fileInput = tag === 'input' && type === 'file';
      if (!isVisible(el) && !fileInput) continue;
      let id = el.getAttribute('data-talentry-id');
      if (!id || !idPattern.test(id)) {
        id = `${prefix}${++counter}`;
        el.setAttribute('data-talentry-id', id);
      }
      const text = (
        tag === 'button' ||
        tag === 'a' ||
        tag === 'summary' ||
        el.getAttribute('role')
      ) ? textOf(el) : '';
      const label = labelOf(el) || text;
      let value = null;
      let hasValue = false;
      if (tag === 'select') {
        value = el.multiple
          ? Array.from(el.selectedOptions).map((option) => option.value).join(', ')
          : el.value;
        hasValue = el.multiple
          ? el.selectedOptions.length > 0
          : el.value !== '';
      } else if (fileInput) {
        hasValue = el.files.length > 0;
      } else if (tag === 'input' && (type === 'checkbox' || type === 'radio')) {
        hasValue = el.checked;
      } else if (tag === 'input' && type === 'password') {
        hasValue = el.value !== '';
      } else if (tag === 'input' || tag === 'textarea') {
        value = el.value;
        hasValue = el.value !== '';
      } else if (el.isContentEditable) {
        value = textOf(el);
        hasValue = value !== '';
      }
      let options = null;
      let optionsTruncated = false;
      if (tag === 'select') {
        const all = Array.from(el.options);
        options = all.slice(0, arg.maxOptions).map((option) => ({
          value: option.value,
          label: clean(option.label || option.textContent),
          disabled: option.disabled,
        }));
        optionsTruncated = all.length > arg.maxOptions;
      }
      const ariaChecked = el.getAttribute('aria-checked');
      elements.push({
        id,
        tag,
        type: (labelControl ? labelControl.type : type) || null,
        role: el.getAttribute('role') || null,
        label: label || null,
        name: el.getAttribute('name') || null,
        placeholder: el.getAttribute('placeholder') || null,
        text: text || null,
        value: value === '' ? null : value,
        href: tag === 'a' ? (el.href || null) : null,
        autocomplete: el.getAttribute('autocomplete') || null,
        accept: fileInput ? (el.getAttribute('accept') || null) : null,
        required: Boolean(el.required) ||
          el.getAttribute('aria-required') === 'true' ||
          Boolean(labelControl && labelControl.required),
        disabled: Boolean(el.disabled) ||
          el.getAttribute('aria-disabled') === 'true' ||
          Boolean(el.closest('fieldset[disabled]')) ||
          Boolean(labelControl && labelControl.disabled),
        read_only: Boolean(el.readOnly) ||
          el.getAttribute('aria-readonly') === 'true',
        checked: (tag === 'input' && (type === 'checkbox' || type === 'radio'))
          ? el.checked
          : (labelControl
              ? Boolean(labelControl.checked)
              : (ariaChecked === 'true'
                  ? true
                  : (ariaChecked === 'false' ? false : null))),
        multiple: (tag === 'select' || fileInput)
          ? Boolean(el.multiple)
          : null,
        visible: isVisible(el),
        editable: Boolean(el.isContentEditable),
        has_value: hasValue,
        options,
        options_truncated: optionsTruncated,
        section: sectionOf(labelControl || el) || null,
        maxlength: el.maxLength > 0 ? el.maxLength : null,
      });
    }
  };
  collect(document);
  window.__talentryIdCounter = counter;
  const bodyText = document.body ? document.body.innerText : '';
  const text = pageText(bodyText);

  const errors = [];
  for (const el of document.querySelectorAll(
    '[role="alert"], .error, .errors, [class*="error"], [class*="Error"], [aria-invalid="true"]'
  )) {
    if (!isVisible(el)) continue;
    const message = textOf(el);
    if (message && message.length < 200 && !errors.includes(message)) {
      errors.push(message);
    }
  }

  const captcha = document.querySelector(
    '.g-recaptcha:not([data-size="invisible"]), .h-captcha, .cf-turnstile, ' +
    'iframe[src*="hcaptcha"], iframe[src*="turnstile"], ' +
    'iframe[title*="recaptcha challenge"]'
  );
  const signals = {
    captcha: Boolean(captcha),
    login: Boolean(document.querySelector('input[type="password"]')),
    text_fields: elements.filter((el) => (
      ['text', 'textarea', 'combobox', 'email', 'tel', 'url', 'password'].includes(el.type) ||
      ['textbox', 'searchbox', 'combobox'].includes(el.role)
    )).length,
    has_file: elements.some((el) => el.tag === 'input' && el.type === 'file'),
    confirmation: confirmationRe.test(bodyText),
    bot_block: botRe.test(document.title + ' ' + bodyText.slice(0, 400)),
  };

  return {
    text: text.slice(0, maxText),
    text_truncated: text.length > maxText,
    ready_state: document.readyState,
    elements,
    errors: errors.slice(0, 10),
    signals,
    truncated,
  };
}
"""

SELECT_OPTIONS_JS = """
(el) => Array.from(el.options).map((option) => ({
  value: option.value,
  label: (option.label || option.textContent || '').trim(),
  disabled: option.disabled,
}))
"""


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _element_from_dict(data: dict[str, Any], frame_index: int) -> ElementInfo:
    options = [
        OptionInfo(
            value=str(option.get("value") or ""),
            label=str(option.get("label") or ""),
            disabled=bool(option.get("disabled")),
        )
        for option in (data.get("options") or [])
    ]
    checked = data.get("checked")
    multiple = data.get("multiple")
    return ElementInfo(
        id=str(data["id"]),
        tag=str(data.get("tag") or ""),
        type=_optional_str(data.get("type")),
        role=_optional_str(data.get("role")),
        label=_optional_str(data.get("label")),
        name=_optional_str(data.get("name")),
        placeholder=_optional_str(data.get("placeholder")),
        text=_optional_str(data.get("text")),
        value=_optional_str(data.get("value")),
        href=_optional_str(data.get("href")),
        autocomplete=_optional_str(data.get("autocomplete")),
        accept=_optional_str(data.get("accept")),
        required=bool(data.get("required")),
        disabled=bool(data.get("disabled")),
        read_only=bool(data.get("read_only")),
        checked=None if checked is None else bool(checked),
        multiple=None if multiple is None else bool(multiple),
        visible=bool(data.get("visible", True)),
        editable=bool(data.get("editable")),
        has_value=bool(data.get("has_value")),
        options=options or None,
        options_truncated=bool(data.get("options_truncated")),
        section=_optional_str(data.get("section")),
        maxlength=(
            int(data["maxlength"])
            if isinstance(data.get("maxlength"), (int, float))
            else None
        ),
        frame_index=frame_index,
    )


class PageTools:
    """Actions an agent can take on one Playwright page."""

    def __init__(self, page: Page, *, timeout_ms: int = 30_000) -> None:
        self.page = page
        self.timeout_ms = timeout_ms
        self._id_token = uuid4().hex[:8]
        self._element_frames: dict[str, int] = {}
        self._elements: dict[str, ElementInfo] = {}
        self._last_inspection: PageInspection | None = None
        self._allow_submit = False

    async def inspect_page(self) -> PageInspection:
        """Return the visible interactive elements and text on the page."""
        if self.page.is_closed():
            raise ToolError("The page is closed.")
        inspect_timeout = (
            min(self.timeout_ms, 5_000) if self.timeout_ms > 0 else 5_000
        )
        try:
            await self.page.wait_for_load_state(
                "domcontentloaded",
                timeout=inspect_timeout,
            )
        except PlaywrightError:
            pass

        self._element_frames.clear()
        self._elements.clear()
        frames: list[FrameInfo] = []
        elements: list[ElementInfo] = []
        text = ""
        ready_state = "unknown"
        text_truncated = False
        elements_truncated = False
        errors: list[str] = []
        signals = PageSignals()

        for index, frame in enumerate(self.page.frames):
            try:
                data = await frame.evaluate(
                    INSPECT_JS,
                    {
                        "token": self._id_token,
                        "frameIndex": index,
                        "maxElements": MAX_ELEMENTS_PER_FRAME,
                        "maxOptions": MAX_OPTIONS,
                        "maxText": MAX_TEXT if index == 0 else MAX_FRAME_TEXT,
                    },
                )
            except PlaywrightError as exc:
                logger.debug("Skipping frame %d: %s", index, exc)
                continue
            if not isinstance(data, dict):
                continue

            frame_text = str(data.get("text") or "")
            frame_elements = [
                _element_from_dict(item, index)
                for item in (data.get("elements") or [])
                if isinstance(item, dict)
            ]
            if index == 0:
                text = frame_text
                ready_state = str(data.get("ready_state") or "unknown")
                text_truncated = bool(data.get("text_truncated"))
                errors = [
                    str(item)
                    for item in (data.get("errors") or [])
                    if isinstance(item, str)
                ][:10]
                signals = PageSignals.model_validate(
                    data.get("signals") or {}
                )
            if index > 0 and not frame_text and not frame_elements:
                continue

            frames.append(
                FrameInfo(
                    index=index,
                    name=frame.name or None,
                    url=frame.url,
                    is_main=index == 0,
                    text=frame_text,
                    text_truncated=bool(data.get("text_truncated")),
                )
            )
            elements.extend(frame_elements)
            elements_truncated = elements_truncated or bool(data.get("truncated"))

        if len(elements) > MAX_ELEMENTS:
            elements = elements[:MAX_ELEMENTS]
            elements_truncated = True

        for element in elements:
            self._element_frames[element.id] = element.frame_index
            self._elements[element.id] = element

        try:
            title = await self.page.title()
        except PlaywrightError:
            title = ""

        logger.debug(
            "Inspected %s: %d elements across %d frames",
            self.page.url,
            len(elements),
            len(frames),
        )
        inspection = PageInspection(
            url=self.page.url,
            title=title,
            text=text,
            ready_state=ready_state,
            elements=elements,
            frames=frames,
            errors=errors,
            signals=signals,
            elements_truncated=elements_truncated,
            text_truncated=text_truncated,
        )
        self._last_inspection = inspection
        return inspection

    async def navigate(self, url: str) -> ActionResult:
        """Open an http(s) URL in the page."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                raise ToolError("Only http and https URLs can be opened.")
            await self.page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            self._clear_element_map()
            return await self._success(f"Opened {self.page.url}.")
        except (ToolError, PlaywrightError) as exc:
            return self._failure(None, exc)

    async def fill_field(self, element_id: str, value: str) -> ActionResult:
        """Replace the value of an input, textarea, or contenteditable field."""
        try:
            locator, info = await self._require_element(element_id)
            tag = str(await locator.evaluate("el => el.tagName.toLowerCase()"))
            field_type = str(
                await locator.evaluate("el => (el.type || '').toLowerCase()")
            )
            label = self._label(info, element_id)
            if tag == "select":
                raise ToolError(f"'{label}' is a dropdown. Use select_option.")
            if tag == "input" and field_type in {"checkbox", "radio"}:
                raise ToolError(f"'{label}' is a checkbox or radio. Use set_checked.")
            if tag == "input" and field_type == "file":
                raise ToolError(f"'{label}' is a file input. Use upload_file.")
            if info is not None and info.tag == "label":
                raise ToolError(f"'{label}' is a clickable label. Use click_element.")
            if info is not None and info.role in {"checkbox", "radio", "switch"}:
                raise ToolError(
                    f"'{label}' is a custom control. Use click_element."
                )
            self._require_visible(info, label)
            self._require_enabled(info, label)
            if info and info.read_only:
                raise ToolError(f"'{label}' is read-only.")
            is_contenteditable = await locator.evaluate(
                "el => Boolean(el.isContentEditable)"
            )
            if tag not in {"input", "textarea"} and not is_contenteditable:
                if info is not None and info.role == "combobox":
                    raise ToolError(
                        f"'{label}' is a custom dropdown. "
                        "Click it, then inspect the options."
                    )
                raise ToolError(f"'{label}' is not editable.")
            await locator.fill(value, timeout=self.timeout_ms)
            return await self._success(f"Filled '{label}'.", element_id)
        except (ToolError, PlaywrightError) as exc:
            return self._failure(element_id, exc)

    async def click_element(self, element_id: str) -> ActionResult:
        """Click a visible, enabled element."""
        try:
            locator, info = await self._require_element(element_id)
            label = self._label(info, element_id)
            if info is not None and info.tag == "select":
                raise ToolError(
                    f"'{label}' is a native dropdown. Use select_option."
                )
            if info is not None and info.tag == "input" and info.type == "file":
                raise ToolError(f"'{label}' is a file input. Use upload_file.")
            self._require_visible(info, label)
            self._require_enabled(info, label)
            if not self._allow_submit and self._looks_like_submit(info):
                inspection = self._last_inspection or await self.inspect_page()
                if (
                    inspection.signals.text_fields >= 2
                    or inspection.signals.has_file
                ):
                    raise SubmitBlocked(
                        f"Refused to click '{label}': it would submit the "
                        "application. Submission only happens after approval."
                    )
            before = self.page.url
            await locator.click(timeout=self.timeout_ms)
            self._clear_if_navigated(before)
            return await self._success(f"Clicked '{label}'.", element_id)
        except (ToolError, PlaywrightError) as exc:
            return self._failure(element_id, exc)

    async def select_option(self, element_id: str, option: str) -> ActionResult:
        """Select an option in a native dropdown by label or value."""
        try:
            locator, info = await self._require_element(element_id)
            tag = str(await locator.evaluate("el => el.tagName.toLowerCase()"))
            label = self._label(info, element_id)
            if tag != "select":
                raise ToolError(
                    f"'{label}' is not a native dropdown. "
                    "Click it, then inspect the options."
                )
            self._require_visible(info, label)
            self._require_enabled(info, label)

            try:
                await locator.select_option(label=option, timeout=self.timeout_ms)
            except PlaywrightError:
                try:
                    await locator.select_option(value=option, timeout=self.timeout_ms)
                except PlaywrightError:
                    options = await locator.evaluate(SELECT_OPTIONS_JS)
                    normalized = option.strip().casefold()
                    match = next(
                        (
                            item
                            for item in options
                            if str(item.get("label") or "").strip().casefold()
                            == normalized
                        ),
                        None,
                    )
                    if match is None:
                        match = next(
                            (
                                item
                                for item in options
                                if str(item.get("value") or "").strip().casefold()
                                == normalized
                            ),
                            None,
                        )
                    if match is None:
                        available = [
                            str(item.get("label") or item.get("value") or "")
                            for item in options
                            if not item.get("disabled")
                        ][:20]
                        detail = ", ".join(available) or "none"
                        raise ToolError(
                            f"Option '{option}' not found in '{label}'. "
                            f"Available options: {detail}."
                        )
                    await locator.select_option(
                        value=str(match.get("value") or ""),
                        timeout=self.timeout_ms,
                    )
            return await self._success(f"Selected '{option}' in '{label}'.", element_id)
        except (ToolError, PlaywrightError) as exc:
            return self._failure(element_id, exc)

    async def set_checked(self, element_id: str, checked: bool) -> ActionResult:
        """Check or uncheck a checkbox, or select a radio button."""
        try:
            locator, info = await self._require_element(element_id)
            tag = str(await locator.evaluate("el => el.tagName.toLowerCase()"))
            field_type = str(
                await locator.evaluate("el => (el.type || '').toLowerCase()")
            )
            label = self._label(info, element_id)
            if tag != "input" or field_type not in {"checkbox", "radio"}:
                raise ToolError(
                    f"'{label}' is not a native checkbox or radio button. "
                    "Use click_element for custom controls."
                )
            self._require_visible(info, label)
            self._require_enabled(info, label)
            if checked:
                await locator.check(timeout=self.timeout_ms)
            elif field_type == "radio":
                raise ToolError("Radio buttons cannot be unchecked directly.")
            else:
                await locator.uncheck(timeout=self.timeout_ms)
            verb = "Checked" if checked else "Unchecked"
            return await self._success(f"{verb} '{label}'.", element_id)
        except (ToolError, PlaywrightError) as exc:
            return self._failure(element_id, exc)

    async def upload_file(
        self,
        element_id: str,
        files: str | Path | Sequence[str | Path],
    ) -> ActionResult:
        """Set the files on a file input. Hidden file inputs are supported."""
        try:
            locator, info = await self._require_element(element_id)
            if isinstance(files, (str, Path)):
                paths = [Path(files)]
            else:
                paths = [Path(path) for path in files]
            if not paths:
                raise ToolError("No files were provided.")
            missing = [str(path) for path in paths if not path.is_file()]
            if missing:
                raise ToolError(f"File not found: {', '.join(missing)}.")
            tag = str(await locator.evaluate("el => el.tagName.toLowerCase()"))
            field_type = str(
                await locator.evaluate("el => (el.type || '').toLowerCase()")
            )
            label = self._label(info, element_id)
            if tag != "input" or field_type != "file":
                raise ToolError(f"'{label}' is not a file input.")
            self._require_enabled(info, label)
            await locator.set_input_files(
                [str(path) for path in paths],
                timeout=self.timeout_ms,
            )
            return await self._success(
                f"Uploaded {len(paths)} file(s) to '{label}'.",
                element_id,
            )
        except (ToolError, PlaywrightError) as exc:
            return self._failure(element_id, exc)

    async def press_key(self, element_id: str, key: str) -> ActionResult:
        """Focus an element and press a key, such as Enter or Tab."""
        try:
            locator, info = await self._require_element(element_id)
            label = self._label(info, element_id)
            self._require_visible(info, label)
            self._require_enabled(info, label)
            before = self.page.url
            await locator.press(key, timeout=self.timeout_ms)
            self._clear_if_navigated(before)
            return await self._success(f"Pressed '{key}' on '{label}'.", element_id)
        except (ToolError, PlaywrightError) as exc:
            return self._failure(element_id, exc)

    async def select_combobox(self, element_id: str, option: str) -> ActionResult:
        """Open a custom dropdown, type the option, and click the match."""
        try:
            locator, info = await self._require_element(element_id)
            label = self._label(info, element_id)
            self._require_visible(info, label)
            self._require_enabled(info, label)
            frame = self.page.frames[self._element_frames[element_id]]
            await locator.click(timeout=self.timeout_ms)
            try:
                await locator.fill(option, timeout=2_000)
            except PlaywrightError:
                await locator.press_sequentially(option, delay=20)
            choice = frame.get_by_role(
                "option",
                name=re.compile(re.escape(option), re.IGNORECASE),
            ).first
            await choice.wait_for(state="visible", timeout=3_000)
            await choice.click(timeout=self.timeout_ms)
            return await self._success(
                f"Selected '{option}' in '{label}'.",
                element_id,
            )
        except (ToolError, PlaywrightError) as exc:
            return self._failure(element_id, exc)

    async def allow_submit(self) -> None:
        """Allow submit-like clicks for the rest of this page."""
        self._allow_submit = True
        for frame in self.page.frames:
            try:
                await frame.evaluate("window.__talentryAllowSubmit = true")
            except PlaywrightError:
                pass

    async def blocked_submits(self) -> int:
        """How many native form submits the guard stopped."""
        total = 0
        for frame in self.page.frames:
            try:
                total += int(
                    await frame.evaluate("window.__talentryBlocked || 0")
                )
            except PlaywrightError:
                pass
        return total

    @staticmethod
    def _looks_like_submit(info: ElementInfo | None) -> bool:
        if info is None:
            return False
        text = info.text or info.label or ""
        if NEXT_RE.match(text):
            return False
        if info.tag == "input" and info.type == "submit":
            return True
        return bool(SUBMIT_RE.search(text))

    def _resolve(
        self,
        element_id: str,
    ) -> tuple[Locator, ElementInfo | None]:
        frame_index = self._element_frames.get(element_id)
        if frame_index is None:
            raise ToolError(
                f"Unknown element id '{element_id}'. Call inspect_page again."
            )
        frames = self.page.frames
        if frame_index >= len(frames):
            raise ToolError(
                f"The frame for '{element_id}' is gone. Call inspect_page again."
            )
        locator = frames[frame_index].locator(
            f'[data-talentry-id="{element_id}"]'
        ).first
        return locator, self._elements.get(element_id)

    async def _require_element(
        self,
        element_id: str,
    ) -> tuple[Locator, ElementInfo | None]:
        locator, info = self._resolve(element_id)
        if await locator.count() == 0:
            raise ToolError(
                f"Element '{element_id}' is no longer on the page. "
                "Call inspect_page again."
            )
        return locator, info

    def _label(self, info: ElementInfo | None, element_id: str) -> str:
        if info is None:
            return element_id
        return (
            info.label
            or info.name
            or info.placeholder
            or info.text
            or element_id
        )

    def _require_visible(self, info: ElementInfo | None, label: str) -> None:
        if info is not None and not info.visible:
            raise ToolError(f"'{label}' is not visible.")

    def _require_enabled(self, info: ElementInfo | None, label: str) -> None:
        if info is not None and info.disabled:
            raise ToolError(f"'{label}' is disabled.")

    def _clear_element_map(self) -> None:
        self._element_frames.clear()
        self._elements.clear()

    def _clear_if_navigated(self, before: str) -> None:
        if self.page.url != before:
            self._clear_element_map()

    async def _page_state(self) -> tuple[str, str | None]:
        url = self.page.url
        try:
            title = await self.page.title()
        except PlaywrightError:
            title = None
        return url, title

    async def _success(
        self,
        message: str,
        element_id: str | None = None,
    ) -> ActionResult:
        url, title = await self._page_state()
        return ActionResult(
            ok=True,
            message=message,
            element_id=element_id,
            url=url,
            title=title,
        )

    def _failure(
        self,
        element_id: str | None,
        exc: Exception,
    ) -> ActionResult:
        message = str(exc).strip() or exc.__class__.__name__
        logger.debug("Browser tool failed for %s: %s", element_id or "page", message)
        return ActionResult(
            ok=False,
            message=message,
            element_id=element_id,
            url=self.page.url,
        )
