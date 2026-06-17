from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel, HttpUrl
from app.db.database import get_db
from app.models.site import Site
from app.models.check import CheckLog
from app.models.user import User
from app.api.auth import get_current_active_user
from app.core.config import settings
from app.services.auth import get_max_sites_for_user
from app.services.scheduler import process_site_check
from app.services.ai_analysis import suggest_response_threshold
from app.services.events import log_product_event
from app.services.audit import write_audit_log
from sqlalchemy import delete as sql_delete

router = APIRouter(prefix="/sites", tags=["sites"])


class SiteCreate(BaseModel):
    url: str
    name: Optional[str] = None
    check_interval: int = 60
    monitor_availability: bool = True
    monitor_response_time: bool = True
    monitor_content_changes: bool = False
    response_time_threshold: float = 5.0
    alert_on_down: bool = True
    alert_on_slow: bool = True
    alert_on_change: bool = True


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    check_interval: Optional[int] = None
    is_active: Optional[bool] = None
    monitor_availability: Optional[bool] = None
    monitor_response_time: Optional[bool] = None
    monitor_content_changes: Optional[bool] = None
    response_time_threshold: Optional[float] = None
    alert_on_down: Optional[bool] = None
    alert_on_slow: Optional[bool] = None
    alert_on_change: Optional[bool] = None


def site_to_dict(site: Site) -> dict:
    return {
        "id": site.id,
        "url": site.url,
        "name": site.name,
        "check_interval": site.check_interval,
        "is_active": site.is_active,
        "monitor_availability": site.monitor_availability,
        "monitor_response_time": site.monitor_response_time,
        "monitor_content_changes": site.monitor_content_changes,
        "response_time_threshold": site.response_time_threshold,
        "last_status": site.last_status,
        "last_response_time": site.last_response_time,
        "last_checked_at": site.last_checked_at.isoformat() if site.last_checked_at else None,
        "next_check_at": site.next_check_at.isoformat() if site.next_check_at else None,
        "alert_on_down": site.alert_on_down,
        "alert_on_slow": site.alert_on_slow,
        "alert_on_change": site.alert_on_change,
        "created_at": site.created_at.isoformat() if site.created_at else None,
    }


@router.get("/")
async def list_sites(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Site).where(Site.user_id == user.id))
    sites = result.scalars().all()
    return [site_to_dict(s) for s in sites]


@router.post("/")
async def create_site(
    req: SiteCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    # Count existing sites
    count_result = await db.execute(
        select(func.count(Site.id)).where(Site.user_id == user.id)
    )
    count = count_result.scalar()

    max_sites = get_max_sites_for_user(user)
    if count >= max_sites:
        raise HTTPException(
            status_code=403,
            detail=f"Free tier allows {settings.FREE_TIER_MAX_SITES} site(s). Upgrade to Pro for more."
            if not user.is_paid else f"Maximum {max_sites} sites reached."
        )

    # Enforce minimum interval
    min_interval = settings.PAID_TIER_MIN_INTERVAL if user.is_paid else settings.FREE_TIER_MIN_INTERVAL
    check_interval = max(req.check_interval, min_interval)

    # Content monitoring is paid only
    monitor_content = req.monitor_content_changes and user.is_paid

    site = Site(
        user_id=user.id,
        url=str(req.url),
        name=req.name or req.url,
        check_interval=check_interval,
        monitor_availability=req.monitor_availability,
        monitor_response_time=req.monitor_response_time,
        monitor_content_changes=monitor_content,
        response_time_threshold=req.response_time_threshold,
        alert_on_down=req.alert_on_down,
        alert_on_slow=req.alert_on_slow,
        alert_on_change=req.alert_on_change,
        last_status="unknown",
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)

    await write_audit_log(
        db,
        action="site_created",
        resource_type="site",
        actor_user_id=user.id,
        resource_id=str(site.id),
        new_value={"url": site.url, "name": site.name, "check_interval": site.check_interval},
    )

    if count == 0:
        await log_product_event(db, "first_site_added", user.id, {"site_id": site.id})
        await db.commit()

    return site_to_dict(site)


@router.patch("/{site_id}")
async def update_site(
    site_id: int,
    req: SiteUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    site = await db.get(Site, site_id)
    if not site or site.user_id != user.id:
        raise HTTPException(status_code=404, detail="Site not found")

    min_interval = settings.PAID_TIER_MIN_INTERVAL if user.is_paid else settings.FREE_TIER_MIN_INTERVAL

    old = site_to_dict(site)
    for field, value in req.model_dump(exclude_none=True).items():
        if field == "check_interval":
            value = max(value, min_interval)
        if field == "monitor_content_changes" and not user.is_paid:
            value = False
        setattr(site, field, value)

    await db.commit()
    await db.refresh(site)
    await write_audit_log(
        db,
        action="site_updated",
        resource_type="site",
        actor_user_id=user.id,
        resource_id=str(site.id),
        old_value=old,
        new_value=site_to_dict(site),
    )
    await db.commit()
    return site_to_dict(site)

@router.delete("/{site_id}")
async def delete_site(
    site_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    site = await db.get(Site, site_id)
    if not site or site.user_id != user.id:
        raise HTTPException(status_code=404, detail="Site not found")
    
    old = site_to_dict(site)
    # Delete logs first
    await db.execute(sql_delete(CheckLog).where(CheckLog.site_id == site_id))
    # Then delete the site itself
    await db.delete(site)
    await write_audit_log(
        db,
        action="site_deleted",
        resource_type="site",
        actor_user_id=user.id,
        resource_id=str(site_id),
        old_value=old,
    )
    await db.commit()
    return {"ok": True}


@router.post("/{site_id}/check-now")
async def check_now(
    site_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    site = await db.get(Site, site_id)
    if not site or site.user_id != user.id:
        raise HTTPException(status_code=404, detail="Site not found")
    await process_site_check(site_id)
    await db.refresh(site)
    return site_to_dict(site)


@router.get("/{site_id}/logs")
async def get_logs(
    site_id: int,
    limit: int = 50,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    site = await db.get(Site, site_id)
    if not site or site.user_id != user.id:
        raise HTTPException(status_code=404, detail="Site not found")

    result = await db.execute(
        select(CheckLog)
        .where(CheckLog.site_id == site_id)
        .order_by(CheckLog.checked_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "checked_at": l.checked_at.isoformat(),
            "is_up": l.is_up,
            "status_code": l.status_code,
            "response_time": l.response_time,
            "error_message": l.error_message,
            "content_changed": l.content_changed,
            "alert_sent": l.alert_sent,
            "email_sent": l.email_sent,
            "alert_type": l.alert_type,
        }
        for l in logs
    ]


@router.get("/{site_id}/ai-threshold")
async def ai_suggest_threshold(
    site_id: int,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyzes the site's response time history and suggests a smart alert threshold.
    Uses local statistics (no AI tokens) for numbers; one small Groq call for phrasing.
    """
    site = await db.get(Site, site_id)
    if not site or site.user_id != user.id:
        raise HTTPException(status_code=404, detail="Site not found")

    result = await db.execute(
        select(CheckLog.response_time).where(
            and_(
                CheckLog.site_id == site_id,
                CheckLog.is_up == True,
                CheckLog.response_time != None,
            )
        )
        .order_by(CheckLog.checked_at.desc())
        .limit(50)
    )
    times = [row[0] for row in result.all()]

    suggestion = await suggest_response_threshold(
        site_name=site.name or site.url,
        site_url=site.url,
        response_times=times,
    )
    suggestion["current_threshold"] = site.response_time_threshold
    return suggestion
