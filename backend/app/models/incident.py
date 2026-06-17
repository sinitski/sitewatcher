from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, func, Text
from app.db.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    status = Column(String, nullable=False, default="open")  # open | resolved

    trigger_type = Column(String, nullable=True)  # down | slow | changed
    status_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    checks_during_incident = Column(Integer, nullable=False, default=0)
    resolved_in_minutes = Column(Float, nullable=True)
