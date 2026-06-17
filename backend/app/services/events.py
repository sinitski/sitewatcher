from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.product_event import ProductEvent


async def log_product_event(db: AsyncSession, event_name: str, user_id: int | None = None, props: dict[str, Any] | None = None):
    db.add(ProductEvent(user_id=user_id, event_name=event_name, event_props=props or {}))
