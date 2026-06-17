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

    # API security
    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://localhost:3000,https://sitewatcher-six.vercel.app,https://sitewatch-fe.onrender.com"
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 30
    RATE_LIMIT_REGISTER_PER_MINUTE: int = 10
    RATE_LIMIT_VERIFICATION_PER_MINUTE: int = 10

    # Enterprise identity and provisioning
    OIDC_AUTH_URL: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_REDIRECT_URI: str = ""
    SCIM_BEARER_TOKEN: str = ""

    # Data retention
    LOG_RETENTION_DAYS: int = 90

    # Monitoring reliability and alert noise controls
    SCHEDULER_MAX_CONCURRENT_CHECKS: int = 20
    CHECK_RETRY_COUNT: int = 1
    CHECK_RETRY_BACKOFF_SECONDS: int = 2
    NEXT_CHECK_JITTER_SECONDS: int = 20
    CONTENT_CHANGE_ALERT_COOLDOWN_MINUTES: int = 30
    CHECK_LOCATIONS: str = "edge-a,edge-b"

    # Free tier limits
    FREE_TIER_MAX_SITES: int = 1
    FREE_TIER_MIN_INTERVAL: int = 60  # minutes

    # Paid tier limits
    PAID_TIER_MAX_SITES: int = 50
    PAID_TIER_MIN_INTERVAL: int = 1  # minute

    class Config:
        env_file = ".env"


settings = Settings()
