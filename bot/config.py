"""Centralised configuration, loaded from environment variables / .env.

Everything the app needs to run is read here once and shared as a singleton
`settings` object. See `.env.example` for the full list of keys.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")

    # --- Anthropic ---
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-opus-4-8", alias="ANTHROPIC_MODEL")
    anthropic_effort: str = Field(default="medium", alias="ANTHROPIC_EFFORT")

    # --- Database ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./profolio.db", alias="DATABASE_URL"
    )

    # --- Quota / pricing ---
    free_rewrites: int = Field(default=3, alias="FREE_REWRITES")

    # --- Razorpay ---
    razorpay_key_id: str = Field(default="", alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(default="", alias="RAZORPAY_KEY_SECRET")
    razorpay_webhook_secret: str = Field(default="", alias="RAZORPAY_WEBHOOK_SECRET")
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")

    # --- Telegram Stars ---
    enable_telegram_stars: bool = Field(default=True, alias="ENABLE_TELEGRAM_STARS")

    # --- Webhook server ---
    webhook_host: str = Field(default="0.0.0.0", alias="WEBHOOK_HOST")
    webhook_port: int = Field(default=8080, alias="WEBHOOK_PORT")

    # --- Privacy ---
    user_id_hash_salt: str = Field(default="change-me", alias="USER_ID_HASH_SALT")
    file_retention_hours: int = Field(default=24, alias="FILE_RETENTION_HOURS")

    # --- Misc ---
    data_dir: Path = Field(default=Path("./data"), alias="DATA_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def razorpay_enabled(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
