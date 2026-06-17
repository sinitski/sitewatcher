from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, JSON
from app.db.database import Base


class ProductEvent(Base):
    __tablename__ = "product_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    event_name = Column(String, nullable=False, index=True)
    event_props = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
