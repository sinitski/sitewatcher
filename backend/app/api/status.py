"""
Public and private status endpoints.
GET /api/status/{username}     -> public status page for a user
GET /api/status/me/summary     -> authenticated metrics summary
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from datetime import datetime, timedelta
from app.db.database import get_db
from app.models.user import User
from app.models.site import Site
from app.models.check import CheckLog
from app.models.product_event import ProductEvent
from app.api.auth import get_current_active_user
from app.core.config import settings

router = APIRouter(prefix="/status", tags=["status"])


def uptime_percent(checks: list) -> float:
    if not checks:
        return 100.0
    up = sum(1 for c in checks if c.is_up)
    return round(up / len(checks) * 100, 1)


def incidents_and_mttr_minutes(checks: list[CheckLog]) -> tuple[int, float]:
    if not checks:
        return 0, 0.0

    incidents = 0
    down_started_at = None
    durations: list[float] = []

    for check in checks:
        if not check.is_up and down_started_at is None:
            incidents += 1
            down_started_at = check.checked_at
        elif check.is_up and down_started_at is not None:
            durations.append((check.checked_at - down_started_at).total_seconds() / 60.0)
            down_started_at = None

    if not durations:
        return incidents, 0.0
    return incidents, round(sum(durations) / len(durations), 1)


async def _build_user_status_payload(user: User, db: AsyncSession) -> dict:
    sites_result = await db.execute(
        select(Site).where(Site.user_id == user.id, Site.is_active == True)
    )
    sites = sites_result.scalars().all()

    since_30d = datetime.utcnow() - timedelta(days=30)
    since_7d = datetime.utcnow() - timedelta(days=7)
    since_24h = datetime.utcnow() - timedelta(hours=24)
    output = []

    all_checks_24h: list[CheckLog] = []
    all_checks_7d: list[CheckLog] = []

    for site in sites:
        checks_result = await db.execute(
            select(CheckLog)
            .where(CheckLog.site_id == site.id, CheckLog.checked_at >= since_30d)
            .order_by(CheckLog.checked_at.asc())
        )
        checks = checks_result.scalars().all()

        checks_24h = [c for c in checks if c.checked_at >= since_24h]
        checks_7d = [c for c in checks if c.checked_at >= since_7d]
        incidents_7d, mttr_7d = incidents_and_mttr_minutes(checks_7d)

        all_checks_24h.extend(checks_24h)
        all_checks_7d.extend(checks_7d)

        output.append({
            "id": site.id,
            "name": site.name or site.url,
            "url": site.url,
            "status": site.last_status or "unknown",
            "last_checked": site.last_checked_at.isoformat() if site.last_checked_at else None,
            "last_response_time": site.last_response_time,
            "uptime_30d": uptime_percent(checks),
            "uptime_7d": uptime_percent(checks_7d),
            "uptime_24h": uptime_percent(checks_24h),
            "incidents_7d": incidents_7d,
            "mttr_minutes_7d": mttr_7d,
            "history": [
                {
                    "time": c.checked_at.isoformat(),
                    "is_up": c.is_up,
                    "response_ms": round(c.response_time * 1000) if c.response_time else None,
                }
                for c in checks[-30:]
            ],
        })

    all_up = all(s["status"] == "up" for s in output) if output else False
    any_down = any(s["status"] == "down" for s in output)
    incidents_7d, mttr_7d = incidents_and_mttr_minutes(sorted(all_checks_7d, key=lambda c: c.checked_at))

    return {
        "username": user.telegram_username,
        "overall": "operational" if all_up else ("partial_outage" if any_down else "unknown"),
        "generated_at": datetime.utcnow().isoformat(),
        "overall_metrics": {
            "uptime_24h": uptime_percent(all_checks_24h),
            "uptime_7d": uptime_percent(all_checks_7d),
            "incidents_7d": incidents_7d,
            "mttr_minutes_7d": mttr_7d,
        },
        "sites": output,
    }


@router.get("/{username}")
async def public_status(username: str, db: AsyncSession = Depends(get_db)):
    """
    Public status page for a user's monitored sites.
    Returns uptime stats for the last 30 days.
    No authentication required.
    """
    result = await db.execute(select(User).where(User.status_slug == username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Status page not found")

    payload = await _build_user_status_payload(user, db)
    payload["username"] = username
    return payload


@router.get("/me/summary")
async def me_summary(user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    payload = await _build_user_status_payload(user, db)

    first_incident_result = await db.execute(
        select(CheckLog.id)
        .join(Site, Site.id == CheckLog.site_id)
        .where(
            and_(
                Site.user_id == user.id,
                CheckLog.alert_sent == True,
                CheckLog.alert_type.in_(["down", "slow", "changed", "recovered"]),
            )
        )
        .limit(1)
    )
    first_incident_caught = first_incident_result.scalar_one_or_none() is not None

    event_counts_result = await db.execute(
        select(ProductEvent.event_name)
        .where(ProductEvent.user_id == user.id)
        .order_by(ProductEvent.created_at.asc())
    )
    event_names = [row[0] for row in event_counts_result.all()]

    payload["public_status_url"] = f"{settings.FRONTEND_URL.rstrip('/')}/#/status/{user.status_slug}" if user.status_slug else None
    payload["first_incident_caught"] = first_incident_caught
    payload["referral_code"] = user.referral_code
    payload["funnel"] = {
        "registered": "user_registered" in event_names,
        "first_site_added": "first_site_added" in event_names,
        "first_alert_sent": "first_alert_sent" in event_names,
        "upgraded": user.is_paid,
    }
    return payload
