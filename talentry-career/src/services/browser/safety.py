"""Rules that keep the agent from submitting by accident."""

from __future__ import annotations

import re

SUBMIT_RE = re.compile(
    r"\b(submit|send application|apply|finish|complete|confirm|send)\b",
    re.IGNORECASE,
)
NEXT_RE = re.compile(
    r"^\s*(next|continue|save (and|&) continue|next step)\b",
    re.IGNORECASE,
)
APPLY_RE = re.compile(r"\bapply\b", re.IGNORECASE)
CONFIRM_RE = re.compile(
    r"thank you for (applying|your application|your interest)|"
    r"application (has been |was )?(submitted|received|sent)|"
    r"we(’|')?ve received your application|successfully submitted|"
    r"your application is (in|complete)",
    re.IGNORECASE,
)
BOT_RE = re.compile(
    r"verify you are (a )?human|unusual traffic|checking your browser|"
    r"access denied|just a moment",
    re.IGNORECASE,
)

SUBMIT_GUARD_SCRIPT = """
(() => {
  window.__talentryAllowSubmit = false;
  window.__talentryBlocked = 0;
  window.addEventListener('submit', (event) => {
    if (!window.__talentryAllowSubmit) {
      event.preventDefault();
      event.stopImmediatePropagation();
      window.__talentryBlocked += 1;
    }
  }, true);
})();
"""
