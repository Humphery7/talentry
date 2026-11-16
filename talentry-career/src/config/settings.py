import os
from pathlib import Path
from pydantic_settings import BaseSettings

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set in talentry-career/.env")
    return url


class Settings(BaseSettings):

    app_name: str = "talentry-career 0.1v"
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    # Encrypts each user's own Gemini key at rest. Must match the backend's
    # AI_KEY_SECRET; changing it makes saved keys unreadable (users re-enter).
    AI_KEY_SECRET: str | None = None
    PLAYWRIGHT_CHANNEL: str | None = None
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_TIMEOUT_MS: int = 30_000
    PLAYWRIGHT_SLOW_MO_MS: int = 0
    AGENT_MAX_STEPS: int = 20
    AGENT_MAX_ATTEMPTS: int = 3
    AGENT_POLL_SECONDS: float = 5.0
    AGENT_STALE_MINUTES: int = 5
    # How long one worker may hold an employer page open waiting for the code
    # the site emailed. The worker is busy for this long, so keep it short.
    AGENT_CODE_WAIT_SECONDS: int = 180
    AGENT_CODE_POLL_SECONDS: float = 2.0


settings = Settings()
