import logging
import re
import asyncio
import random
import json
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, and_, delete as sql_delete
import httpx
from app.db.database import AsyncSessionLocal
from app.models.site import Site
from app.models.user import User
from app.models.check import CheckLog
from app.models.incident import Incident
from app.models.product_event import ProductEvent
from app.models.organization_member import OrganizationMember
from app.models.notification_channel import NotificationChannel
from app.models.maintenance_window import MaintenanceWindow
from app.services.checker import check_site
from app.core.config import settings
from app.services.telegram import (
    format_alert_down,
    format_alert_recovered,
    format_alert_slow,
    format_alert_changed,
)
from app.services.email import split_email_list
from app.services.ai_analysis import analyze_downtime, analyze_content_diff
from app.services.weekly_report import send_weekly_reports
from app.services.notification_queue import enqueue_telegram, enqueue_email
from app.services.events import log_product_event

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

_METRICS = {
    "checks_total": 0,
    "checks_failed": 0,
    "alerts_sent_total": 0,
    "alerts_failed_total": 0,
    "email_alerts_sent": 0,
    "telegram_alerts_sent": 0,
    "org_channel_alerts_sent": 0,
}


def metrics_snapshot() -> dict:
    return dict(_METRICS)


async def _get_recent_incidents(db, site_id: int, limit: int = 5) -> list[dict]:
    """Fetch recent downtime incidents for AI pattern analysis."""
    week_ago = datetime.utcnow() - timedelta(days=7)
    result = await db.execute(
        select(CheckLog)
        .where(
            and_(
                CheckLog.site_id == site_id,
                CheckLog.is_up == False,
                CheckLog.checked_at >= week_ago,
            )
        )
        .order_by(CheckLog.checked_at.desc())
        .limit(limit * 3)
    )
    raw = result.scalars().all()

    incidents = []
    seen_windows = set()
    for check in reversed(raw):
        window = check.checked_at.replace(minute=0, second=0, microsecond=0)
        if window not in seen_windows:
            seen_windows.add(window)
            incidents.append({
                "checked_at": check.checked_at,
                "error": check.error_message,
                "duration_min": check.response_time,
            })
    return incidents[-limit:]


async def _free_email_quota_available(db, user_id: int) -> bool:
    day_ago = datetime.utcnow() - timedelta(days=1)
    result = await db.execute(
        select(CheckLog.id)
        .join(Site, Site.id == CheckLog.site_id)
        .where(
            and_(
                Site.user_id == user_id,
                CheckLog.email_sent == True,
                CheckLog.checked_at >= day_ago,
            )
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is None


async def _change_alert_quota_available(db, site_id: int) -> bool:
    cooldown_from = datetime.utcnow() - timedelta(minutes=settings.CONTENT_CHANGE_ALERT_COOLDOWN_MINUTES)
    result = await db.execute(
        select(CheckLog.id)
        .where(
            and_(
                CheckLog.site_id == site_id,
                CheckLog.alert_type == "changed",
                CheckLog.checked_at >= cooldown_from,
            )
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is None


async def _site_in_maintenance(db, user_id: int) -> bool:
    now = datetime.utcnow()
    member_result = await db.execute(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user_id)
    )
    org_ids = [row[0] for row in member_result.all()]
    if not org_ids:
        return False

    mw_result = await db.execute(
        select(MaintenanceWindow.id)
        .where(
            and_(
                MaintenanceWindow.organization_id.in_(org_ids),
                MaintenanceWindow.starts_at <= now,
                MaintenanceWindow.ends_at >= now,
            )
        )
        .limit(1)
    )
    return mw_result.scalar_one_or_none() is not None


async def _dispatch_org_channels(db, user_id: int, alert_payload: dict) -> int:
    member_result = await db.execute(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user_id)
    )
    org_ids = [row[0] for row in member_result.all()]
    if not org_ids:
        return 0

    channels_result = await db.execute(
        select(NotificationChannel)
        .where(
            and_(
                NotificationChannel.organization_id.in_(org_ids),
                NotificationChannel.is_active == True,
            )
        )
    )
    channels = channels_result.scalars().all()
    if not channels:
        return 0

    delivered = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for ch in channels:
            try:
                if ch.channel_type == "slack":
                    r = await client.post(ch.target_url, json={"text": alert_payload.get("text", "SiteWatcher alert")})
                else:
                    headers = {"Content-Type": "application/json"}
                    if ch.secret:
                        headers["X-SiteWatcher-Signature"] = ch.secret
                    r = await client.post(ch.target_url, headers=headers, content=json.dumps(alert_payload))
                if r.status_code < 300:
                    delivered += 1
                    _METRICS["org_channel_alerts_sent"] += 1
            except Exception:
                continue
    return delivered


def _should_retry_check(check_result: dict) -> bool:
    if check_result.get("is_up"):
        return False
    status_code = check_result.get("status_code")
    if status_code is None:
        return True
    return int(status_code) >= 500


async def _run_check_with_retry(url: str) -> dict:
    result = await check_site(url)
    retries = max(0, int(settings.CHECK_RETRY_COUNT))
    if retries <= 0:
        return result

    for attempt in range(1, retries + 1):
        if not _should_retry_check(result):
            break
        await asyncio.sleep(max(1, int(settings.CHECK_RETRY_BACKOFF_SECONDS)) * attempt)
        retry_result = await check_site(url)
        result = retry_result
    return result


async def run_checks():
    """Main scheduler job: find due sites and check them."""
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Site).where(
                and_(
                    Site.is_active == True,
                    (Site.next_check_at == None) | (Site.next_check_at <= now),
                )
            )
        )
        sites = result.scalars().all()

    if not sites:
        return

    _METRICS["checks_total"] += len(sites)

    random.shuffle(sites)
    max_concurrent = max(1, int(settings.SCHEDULER_MAX_CONCURRENT_CHECKS))
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _run_one(site_id: int):
        async with semaphore:
            try:
                await process_site_check(site_id)
            except Exception as e:
                logger.error(f"Error checking site {site_id}: {e}")

    await asyncio.gather(*[_run_one(site.id) for site in sites])


async def purge_old_data():
    cutoff = datetime.utcnow() - timedelta(days=max(7, int(settings.LOG_RETENTION_DAYS)))
    async with AsyncSessionLocal() as db:
        await db.execute(sql_delete(CheckLog).where(CheckLog.checked_at < cutoff))
        await db.execute(sql_delete(ProductEvent).where(ProductEvent.created_at < cutoff))
        await db.execute(
            sql_delete(Incident).where(
                and_(
                    Incident.status == "resolved",
                    Incident.resolved_at != None,
                    Incident.resolved_at < cutoff,
                )
            )
        )
        await db.commit()


async def process_site_check(site_id: int):
    async with AsyncSessionLocal() as db:
        site = await db.get(Site, site_id)
        if not site:
            return

        user_result = await db.execute(select(User).where(User.id == site.user_id))
        user = user_result.scalar_one_or_none()

        check_result = await _run_check_with_retry(site.url)

        is_up = check_result["is_up"]
        response_time = check_result["response_time"]
        content_hash = check_result["content_hash"]
        new_raw_text = check_result.get("raw_text") or ""
        error_message = check_result["error_message"]
        status_code = check_result["status_code"]

        if await _site_in_maintenance(db, site.user_id):
            is_up = True

        prev_status = site.last_status
        prev_hash = site.last_content_hash
        prev_snapshot = site.last_content_snapshot or ""

        incident_result = await db.execute(
            select(Incident)
            .where(
                and_(
                    Incident.site_id == site.id,
                    Incident.status == "open",
                )
            )
            .order_by(Incident.started_at.desc())
            .limit(1)
        )
        open_incident = incident_result.scalar_one_or_none()

        # Determine alert type and build message
        alert_type = None
        alert_text = None

        if not is_up and prev_status != "down":
            alert_type = "down"
            if site.alert_on_down:
                plain_alert = format_alert_down(site.name, site.url, error_message, status_code)
                alert_text = plain_alert
                if user and user.telegram_chat_id:
                    recent_incidents = await _get_recent_incidents(db, site_id)
                    ai_insight = await analyze_downtime(
                        site_name=site.name or site.url,
                        site_url=site.url,
                        error_message=error_message,
                        status_code=status_code,
                        recent_incidents=recent_incidents,
                    )
                    if ai_insight:
                        alert_text = plain_alert + f"\n\n🤖 <i>{ai_insight}</i>"

            if not open_incident:
                open_incident = Incident(
                    site_id=site.id,
                    user_id=site.user_id,
                    trigger_type="down",
                    status="open",
                    status_code=status_code,
                    error_message=error_message,
                    checks_during_incident=1,
                )
                db.add(open_incident)

        elif is_up and prev_status == "down":
            alert_type = "recovered"
            alert_text = format_alert_recovered(site.name, site.url, response_time or 0)
            if open_incident:
                open_incident.status = "resolved"
                open_incident.resolved_at = datetime.utcnow()
                open_incident.resolved_in_minutes = round(
                    (open_incident.resolved_at - open_incident.started_at).total_seconds() / 60.0,
                    1,
                )

        if open_incident and open_incident.status == "open" and not is_up:
            open_incident.checks_during_incident = (open_incident.checks_during_incident or 0) + 1

        elif is_up and site.monitor_response_time and site.alert_on_slow:
            if response_time and response_time > site.response_time_threshold:
                alert_type = "slow"
                alert_text = format_alert_slow(
                    site.name, site.url, response_time, site.response_time_threshold
                )

        # ── Content change detection ──────────────────────────────────────────
        content_changed = False
        if is_up and site.monitor_content_changes and prev_hash and content_hash:
            if prev_hash != content_hash:
                content_changed = True
                can_send_change_alert = await _change_alert_quota_available(db, site.id)
                if not can_send_change_alert:
                    logger.info("Change alert suppressed by cooldown (site_id=%s)", site.id)

                if not alert_type and can_send_change_alert:
                    alert_type = "changed"

                    # Pro-only AI diff analysis (Telegram only)
                    if user and user.is_paid and user.telegram_chat_id and prev_snapshot and new_raw_text:
                        ai_diff = await analyze_content_diff(
                            site_name=site.name or site.url,
                            site_url=site.url,
                            old_text=prev_snapshot,
                            new_text=new_raw_text,
                        )
                        if ai_diff:
                            alert_text = (
                                format_alert_changed(site.name, site.url)
                                + f"\n\n🔍 <i>{ai_diff}</i>"
                            )
                        else:
                            alert_text = format_alert_changed(site.name, site.url)
                    elif site.alert_on_change:
                        alert_text = format_alert_changed(site.name, site.url)

        # Send alert
        telegram_sent = False
        email_sent = False
        if alert_text and user and user.telegram_chat_id:
            telegram_sent = await enqueue_telegram(user.telegram_chat_id, alert_text)
            if telegram_sent:
                _METRICS["telegram_alerts_sent"] += 1

        if alert_text and user and user.email_verified and user.email_alerts_enabled:
            can_send_email = True
            if not user.is_paid:
                can_send_email = await _free_email_quota_available(db, user.id)
                if not can_send_email:
                    logger.info("Free-tier email alert skipped due to daily quota (user_id=%s)", user.id)

            if can_send_email:
                recipients = split_email_list(user.alert_emails) or [user.email]
                subject_map = {
                    "down": f"SiteWatcher alert: {site.name or site.url} is down",
                    "recovered": f"SiteWatcher alert: {site.name or site.url} recovered",
                    "slow": f"SiteWatcher alert: {site.name or site.url} is slow",
                    "changed": f"SiteWatcher alert: {site.name or site.url} changed",
                }
                subject = subject_map.get(alert_type or "down", f"SiteWatcher alert: {site.name or site.url}")
                html_body = alert_text.replace("\n", "<br>")
                text_body = re.sub(r"<[^>]+>", "", alert_text)
                for recipient in recipients:
                    sent = await enqueue_email(recipient, subject, html_body, text_body)
                    email_sent = email_sent or sent
                if email_sent:
                    _METRICS["email_alerts_sent"] += 1

        org_channel_sent = 0
        if alert_text and user:
            org_channel_sent = await _dispatch_org_channels(
                db,
                user.id,
                {
                    "type": alert_type,
                    "site": site.name or site.url,
                    "url": site.url,
                    "text": re.sub(r"<[^>]+>", "", alert_text),
                },
            )

        alert_sent = telegram_sent or email_sent or org_channel_sent > 0
        if alert_sent:
            _METRICS["alerts_sent_total"] += 1
        elif alert_type:
            _METRICS["alerts_failed_total"] += 1
        if alert_sent:
            first_alert_result = await db.execute(
                select(ProductEvent.id)
                .where(
                    and_(
                        ProductEvent.user_id == site.user_id,
                        ProductEvent.event_name == "first_alert_sent",
                    )
                )
                .limit(1)
            )
            if first_alert_result.scalar_one_or_none() is None:
                await log_product_event(db, "first_alert_sent", site.user_id, {"site_id": site.id, "type": alert_type})

        # Log the check
        log = CheckLog(
            site_id=site.id,
            is_up=is_up,
            status_code=status_code,
            response_time=response_time,
            error_message=error_message,
            content_changed=content_changed,
            content_hash=content_hash,
            alert_sent=alert_sent,
            email_sent=email_sent,
            alert_type=alert_type,
        )
        db.add(log)

        # Update site state
        site.last_status = "up" if is_up else "down"
        site.last_response_time = response_time
        site.last_content_hash = content_hash
        # Update the snapshot only when the site is up and we have text
        if is_up and new_raw_text:
            site.last_content_snapshot = new_raw_text[:8000]
        site.last_checked_at = datetime.utcnow()
        jitter_seconds = max(0, int(settings.NEXT_CHECK_JITTER_SECONDS))
        site.next_check_at = datetime.utcnow() + timedelta(
            minutes=site.check_interval,
            seconds=random.randint(0, jitter_seconds) if jitter_seconds else 0,
        )

        await db.commit()


def start_scheduler():
    scheduler.add_job(run_checks, "interval", minutes=1, id="site_checks", replace_existing=True)
    scheduler.add_job(purge_old_data, "cron", hour=3, minute=30, id="purge_old_data", replace_existing=True)
    scheduler.add_job(
        send_weekly_reports,
        "cron",
        day_of_week="mon",
        hour=9,
        minute=0,
        id="weekly_reports",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started (checks + weekly reports)")


def stop_scheduler():
    scheduler.shutdown()