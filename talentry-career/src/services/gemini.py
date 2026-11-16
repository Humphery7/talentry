"""One Gemini client per user key, for the career service.

There is deliberately no global fallback key: every AI call acts for a user and
must be given that user's own key (see `services.ai_keys`).
"""

from __future__ import annotations

import json
from typing import Any

from google import genai

from config.settings import settings
from services.ai_keys import MissingApiKey

_clients: dict[str, genai.Client] = {}


def get_client(api_key: str) -> genai.Client:
    client = _clients.get(api_key)
    if client is None:
        client = genai.Client(api_key=api_key)
        _clients[api_key] = client
    return client


def generate_json(
    *,
    api_key: str | None,
    input: str,
    system_instruction: str,
    schema: dict[str, Any],
    model: str | None = None,
) -> Any:
    """Ask Gemini for JSON that follows `schema` and parse it."""
    if not api_key:
        raise MissingApiKey()
    interaction = get_client(api_key).interactions.create(
        model=model or settings.GEMINI_MODEL,
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
