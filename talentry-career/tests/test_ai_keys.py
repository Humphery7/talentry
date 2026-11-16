import base64
import hashlib
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from services import ai_keys

DEFAULT_SECRET = "dev-secret-change-me"
SALT = b"talentry-user-ai-key"


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def encrypt(plain: str, secret: str = DEFAULT_SECRET) -> str:
    """The same envelope the Express backend writes."""
    key = hashlib.pbkdf2_hmac(
        "sha256", secret.encode(), SALT, 100_000, dklen=32
    )
    iv = b"123456789012"
    sealed = AESGCM(key).encrypt(iv, plain.encode(), None)
    tag, body = sealed[-16:], sealed[:-16]
    return f"v1:{encode(iv)}:{encode(tag)}:{encode(body)}"


class FakeCursor:
    def __init__(self, row: tuple | None) -> None:
        self.row = row

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, sql: str, params: object = None) -> None:
        self.sql = sql
        self.params = params

    def fetchone(self) -> tuple | None:
        return self.row


class FakeConn:
    def __init__(self, row: tuple | None) -> None:
        self.row = row

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.row)


def test_decrypts_what_the_backend_encrypts():
    assert ai_keys.decrypt(encrypt("AIza-user-key")) == "AIza-user-key"


def test_a_different_secret_cannot_read_the_key():
    with pytest.raises(Exception):
        ai_keys.decrypt(encrypt("AIza-user-key", "another-secret"))


def test_for_user_returns_the_plain_key():
    conn = FakeConn((encrypt("AIza-user-key"),))

    assert ai_keys.for_user(conn, "11111111-1111-1111-1111-111111111111") == (
        "AIza-user-key"
    )


def test_for_user_is_none_when_nothing_is_saved():
    assert ai_keys.for_user(FakeConn(None), "user") is None


def test_for_user_is_none_when_the_row_cannot_be_read():
    # A rotated secret must ask again, not break every AI feature.
    conn = FakeConn((encrypt("AIza-user-key", "old-secret"),))

    assert ai_keys.for_user(conn, "user") is None


def test_require_key_explains_how_to_fix_it():
    with pytest.raises(ai_keys.MissingApiKey) as raised:
        ai_keys.require_key(FakeConn(None), "user")

    assert "Settings" in str(raised.value)


def test_require_key_can_name_the_feature():
    with pytest.raises(ai_keys.MissingApiKey) as raised:
        ai_keys.require_key(
            FakeConn(None), "user", "Add a key before starting an application."
        )

    assert "before starting an application" in str(raised.value)
