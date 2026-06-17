from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func, Text
from app.db.database import Base


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    channel_type = Column(String, nullable=False)  # slack | webhook
    name = Column(String, nullable=False)
    target_url = Column(Text, nullable=False)
    secret = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
