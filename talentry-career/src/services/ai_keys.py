"""Read the Gemini API key a user saved in Settings.

The key is encrypted by the Express backend with AES-256-GCM before it is
written to the database. This module is the only place it is decrypted, and it
never logs the plaintext or returns it to a caller that is not acting for that
same user.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache
from uuid import UUID

import psycopg
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config.settings import settings

log = logging.getLogger(__name__)

_SALT = b"talentry-user-ai-key"
# Must match talentry-backend/src/services/ai-settings.service.ts.
_DEFAULT_SECRET = "dev-secret-change-me"
_DEFAULT_MESSAGE = "Add your Gemini API key in Settings to use AI features."


class MissingApiKey(RuntimeError):
    """The user has not saved a Gemini API key, or it cannot be read."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or _DEFAULT_MESSAGE)


@lru_cache(maxsize=1)
def _secret() -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        (settings.AI_KEY_SECRET or _DEFAULT_SECRET).encode(),
        _SALT,
        100_000,
        dklen=32,
    )


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def decrypt(cipher: str) -> str:
    """Undo the backend's AES-256-GCM envelope (`v1:iv:tag:body`)."""
    version, iv, tag, body = cipher.split(":", 3)
    if version != "v1":
        raise ValueError("unknown AI key format")
    plain = AESGCM(_secret()).decrypt(
        _decode(iv), _decode(body) + _decode(tag), None
    )
    return plain.decode()


def for_user(conn: psycopg.Connection, user_id: UUID | str) -> str | None:
    """The user's key, or None when they have not saved one."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT gemini_key_cipher FROM user_ai_settings WHERE user_id = %s",
            (str(user_id),),
        )
        row = cur.fetchone()
    if not row:
        return None
    try:
        return decrypt(row[0])
    except Exception:  # noqa: BLE001 - the user must be able to re-enter it
        # A rotated AI_KEY_SECRET (or a damaged row) makes old keys
        # unreadable. Treat that as "no key" so the UI asks again instead of
        # breaking every AI feature with an opaque error.
        log.warning(
            "Could not read the Gemini key for user %s; asking for it again.",
            user_id,
        )
        return None


def require_key(
    conn: psycopg.Connection,
    user_id: UUID | str,
    message: str | None = None,
) -> str:
    key = for_user(conn, user_id)
    if not key:
        raise MissingApiKey(message)
    return key
