from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./sitewatcher.db"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    TELEGRAM_BOT_TOKEN: str = ""
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"
    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""
    GMAIL_SENDER_EMAIL: str = ""

    # Free tier limits
    FREE_TIER_MAX_SITES: int = 1
    FREE_TIER_MIN_INTERVAL: int = 60  # minutes

    # Paid tier limits
    PAID_TIER_MAX_SITES: int = 50
    PAID_TIER_MIN_INTERVAL: int = 1  # minute

    class Config:
        env_file = ".env"


settings = Settings()
