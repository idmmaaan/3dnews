"""Application settings loaded from environment variables / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── Database ──────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/news3twit"

    # ── X / Twitter (Playwright + Cookies) ────────────────────────────
    X_AUTH_TOKEN: str = ""          # "auth_token" cookie from x.com
    X_CT0: str = ""                 # "ct0" cookie from x.com
    X_ACCOUNTS: str = "CNN"         # comma-separated handles to scrape
    X_TWEETS_PER_ACCOUNT: int = 5

    # ── Gemini ──────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    ENABLE_LLM_SUMMARIZATION: bool = True

    # ── Telegram ──────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHANNEL_ID: str = "@third_twiterova"

    # ── Scheduler ─────────────────────────────────────────────────────
    POLL_INTERVAL_MINUTES: int = 15

    @property
    def x_account_list(self) -> list[str]:
        """Return parsed list of X handles to scrape."""
        return [a.strip() for a in self.X_ACCOUNTS.split(",") if a.strip()]


settings = Settings()
