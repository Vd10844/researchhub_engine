"""Application settings — loaded from environment variables.

All secrets must come from the environment; never hardcode values in code.
Compatible with the parent repo's naming so the engine can be dropped into
the parent's deployment unchanged.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Engine configuration. All fields sourced from environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- runtime ---------------------------------------------------
    RUN_ENV: str = "local"
    ENABLE_FASTAPI_DEBUG: bool = False

    # --- database ---------------------------------------------------
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/researchhub"

    # --- S3 (evidence uploads) --------------------------------------
    AWS_REGION: str = "us-east-1"
    AWS_S3_REGION_NAME: str = "us-east-1"
    S3_ARTIFACTS_BUCKET: str = "researchhub-artifacts"

    # --- Redis / Celery ----------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # --- auth (parent's Cognito) ------------------------------------
    COGNITO_REGION: str | None = None
    COGNITO_USER_POOL_ID: str | None = None
    COGNITO_CLIENT_ID: str | None = None
    COGNITO_ISSUER: str | None = None
    COGNITO_AUDIENCE: str | None = None

    # --- CORS --------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- research defaults -------------------------------------------
    MAX_RETRIES_PER_DOCUMENT: int = 3
    DOCUMENT_TIMEOUT_SECONDS: int = 60

    # --- callback delivery (at-least-once with retry + backoff) ------
    CALLBACK_RETRY_ATTEMPTS: int = 3
    CALLBACK_RETRY_BACKOFF: float = 1.0  # first retry sleep in seconds; doubles
    CALLBACK_RETRY_SLEEP: bool = True  # set false in offline tests to skip sleeps

    # --- HTTP client -------------------------------------------------
    HTTP_TIMEOUT_SECONDS: int = 30

    # --- legacy POC names the service modules still read -----------------
    # (downloader.py / http.py import these directly; keep them in sync with
    #  HTTP_TIMEOUT_SECONDS — they are part of the services' existing contract)
    HTTP_TIMEOUT: int = 30
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"

    # --- staged research jobs ------------------------------------------
    JOBS_DIR: str = str(
        (__import__("pathlib").Path(__file__).resolve().parents[2] / "data" / "jobs")
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

# Module-level aliases the legacy service modules import directly
# (`from ..config import HTTP_TIMEOUT, USER_AGENT`).  Keep these in sync with
# the Settings fields above.
HTTP_TIMEOUT = settings.HTTP_TIMEOUT
USER_AGENT = settings.USER_AGENT