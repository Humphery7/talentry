"""One shared Gemini client for the career service."""

from __future__ import annotations

import json
from typing import Any

from google import genai

from config.settings import settings

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set in talentry-career/.env")
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def generate_json(
    *,
    input: str,
    system_instruction: str,
    schema: dict[str, Any],
) -> Any:
    """Ask Gemini for JSON that follows `schema` and parse it."""
    interaction = get_client().interactions.create(
        model=settings.GEMINI_MODEL,
        input=input,
        system_instruction=system_instruction,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": schema,
        },
        response_mime_type="application/json",
        store=False,
    )
    return json.loads(interaction.output_text or "")
