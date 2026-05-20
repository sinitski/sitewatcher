from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, func, Text
from app.db.database import Base


class CheckLog(Base):
    __tablename__ = "check_logs"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    checked_at = Column(DateTime, server_default=func.now())

    is_up = Column(Boolean, nullable=False)
    status_code = Column(Integer, nullable=True)
    response_time = Column(Float, nullable=True)  # seconds
    error_message = Column(Text, nullable=True)

    content_changed = Column(Boolean, default=False)
    content_hash = Column(String, nullable=True)

    alert_sent = Column(Boolean, default=False)
    email_sent = Column(Boolean, default=False)
    alert_type = Column(String, nullable=True)  # "down" | "slow" | "changed" | "recovered"
