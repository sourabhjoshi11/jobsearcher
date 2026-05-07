"""Application configuration.

Loads settings from environment variables (and a local .env file if present)
using pydantic-settings. Validation happens at startup so a bad config
fails fast instead of crashing halfway through a request.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed app settings.

    Fields that are only used in later phases (Razorpay, webhook URL) are
    optional so Phase 0 / Phase 1 can boot without them.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # don't explode on future env vars we haven't typed yet
    )

    # --- Runtime ------------------------------------------------------------
    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- Telegram -----------------------------------------------------------
    telegram_bot_token: str = Field(
        default="",
        description="Token from @BotFather. Empty is fine for Phase 0 /health check.",
    )
    webhook_url: str = ""

    # --- Database -----------------------------------------------------------
    database_url: str = "postgresql://jobalert:jobalert_dev_pw@localhost:5432/jobalertbot"

    # --- Redis --------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"

    # --- Razorpay (Phase 5) -------------------------------------------------
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor so we parse env vars exactly once per process."""
    return Settings()
