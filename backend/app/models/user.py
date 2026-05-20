from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    telegram_chat_id = Column(String, nullable=True)
    telegram_username = Column(String, nullable=True)
    is_paid = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    # For Telegram-based upgrade flow
    upgrade_token = Column(String, nullable=True, unique=True)
    referral_code = Column(String, nullable=True, unique=True, index=True)
    referred_by_user_id = Column(Integer, nullable=True)
    referral_bonus_sites = Column(Integer, nullable=False, default=0)
    email_verification_token = Column(String, nullable=True, unique=True, index=True)
    email_verification_expires_at = Column(DateTime, nullable=True)
    email_alerts_enabled = Column(Boolean, default=False)
    alert_emails = Column(String, nullable=True)
