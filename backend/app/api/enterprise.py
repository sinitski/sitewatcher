from datetime import datetime, timedelta
from io import StringIO
import csv

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_active_user
from app.core.config import settings
from app.db.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.models.organization_member import OrganizationMember
from app.models.notification_channel import NotificationChannel
from app.models.maintenance_window import MaintenanceWindow
from app.models.audit_log import AuditLog
from app.models.site import Site
from app.models.check import CheckLog
from app.services.audit import write_audit_log
from app.services.scheduler import metrics_snapshot

router = APIRouter(prefix="/enterprise", tags=["enterprise"])


ROLE_WRITE = {"owner", "admin"}
ROLE_READ = {"owner", "admin", "member", "viewer"}


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=120)


class MemberRequest(BaseModel):
    email: str
    role: str = "member"


class UpdateMemberRoleRequest(BaseModel):
    role: str


class ChannelRequest(BaseModel):
    channel_type: str  # slack | webhook
    name: str
    target_url: str
    secret: str | None = None


class MaintenanceRequest(BaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime


def _norm_slug(value: str) -> str:
    v = value.strip().lower()
    v = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in v)
    return v.strip("-")


async def _org_role(db: AsyncSession, org_id: int, user_id: int) -> str | None:
    result = await db.execute(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == user_id,
            )
        )
    )
    member = result.scalar_one_or_none()
    return member.role if member else None


async def _require_org_access(db: AsyncSession, org_id: int, user_id: int, write: bool = False) -> str:
    role = await _org_role(db, org_id, user_id)
    if not role:
        raise HTTPException(status_code=403, detail="Organization access denied")
    if write and role not in ROLE_WRITE:
        raise HTTPException(status_code=403, detail="Write access denied")
    if not write and role not in ROLE_READ:
        raise HTTPException(status_code=403, detail="Read access denied")
    return role


def _uptime_percent(checks: list[CheckLog]) -> float:
    if not checks:
        return 100.0
    up = sum(1 for c in checks if c.is_up)
    return round(up / len(checks) * 100, 2)


@router.post("/orgs")
async def create_org(req: CreateOrgRequest, request: Request, user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    slug = _norm_slug(req.slug)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid slug")

    exists = await db.execute(select(Organization).where(Organization.slug == slug))
    if exists.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug already in use")

    org = Organization(name=req.name.strip(), slug=slug)
    db.add(org)
    await db.flush()

    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role="owner"))
    await write_audit_log(
        db,
        action="org_created",
        resource_type="organization",
        actor_user_id=user.id,
        organization_id=org.id,
        resource_id=str(org.id),
        new_value={"name": org.name, "slug": org.slug},
        request=request,
    )
    await db.commit()
    return {"id": org.id, "name": org.name, "slug": org.slug, "role": "owner"}


@router.get("/orgs")
async def list_orgs(user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(OrganizationMember.user_id == user.id)
    )
    rows = result.all()
    return [{"id": org.id, "name": org.name, "slug": org.slug, "role": role} for org, role in rows]


@router.post("/orgs/{org_id}/members")
async def add_member(org_id: int, req: MemberRequest, request: Request, user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await _require_org_access(db, org_id, user.id, write=True)
    role = req.role.strip().lower()
    if role not in ROLE_READ:
        raise HTTPException(status_code=400, detail="Invalid role")

    user_result = await db.execute(select(User).where(User.email == req.email.strip().lower()))
    member_user = user_result.scalar_one_or_none()
    if not member_user:
        raise HTTPException(status_code=404, detail="User not found")

    existing = await db.execute(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == member_user.id,
            )
        )
    )
    row = existing.scalar_one_or_none()
    if row:
        row.role = role
    else:
        db.add(OrganizationMember(organization_id=org_id, user_id=member_user.id, role=role))

    await write_audit_log(
        db,
        action="org_member_upserted",
        resource_type="organization_member",
        actor_user_id=user.id,
        organization_id=org_id,
        resource_id=f"{org_id}:{member_user.id}",
        new_value={"role": role, "email": member_user.email},
        request=request,
    )
    await db.commit()
    return {"ok": True, "user_id": member_user.id, "role": role}


@router.patch("/orgs/{org_id}/members/{member_user_id}")
async def update_member_role(org_id: int, member_user_id: int, req: UpdateMemberRoleRequest, request: Request, user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await _require_org_access(db, org_id, user.id, write=True)
    role = req.role.strip().lower()
    if role not in ROLE_READ:
        raise HTTPException(status_code=400, detail="Invalid role")

    result = await db.execute(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == member_user_id,
            )
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    old = member.role
    member.role = role
    await write_audit_log(
        db,
        action="org_member_role_changed",
        resource_type="organization_member",
        actor_user_id=user.id,
        organization_id=org_id,
        resource_id=f"{org_id}:{member_user_id}",
        old_value={"role": old},
        new_value={"role": role},
        request=request,
    )
    await db.commit()
    return {"ok": True, "role": role}


@router.get("/orgs/{org_id}/audit")
async def get_audit(org_id: int, limit: int = Query(default=100, le=500), user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await _require_org_access(db, org_id, user.id, write=False)
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.organization_id == org_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "action": l.action,
            "resource_type": l.resource_type,
            "resource_id": l.resource_id,
            "actor_user_id": l.actor_user_id,
            "old_value": l.old_value,
            "new_value": l.new_value,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]


@router.post("/orgs/{org_id}/channels")
async def create_channel(org_id: int, req: ChannelRequest, request: Request, user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await _require_org_access(db, org_id, user.id, write=True)
    ct = req.channel_type.strip().lower()
    if ct not in {"slack", "webhook"}:
        raise HTTPException(status_code=400, detail="channel_type must be slack or webhook")

    channel = NotificationChannel(
        organization_id=org_id,
        channel_type=ct,
        name=req.name.strip(),
        target_url=req.target_url.strip(),
        secret=req.secret,
        is_active=True,
    )
    db.add(channel)
    await db.flush()
    await write_audit_log(
        db,
        action="notification_channel_created",
        resource_type="notification_channel",
        actor_user_id=user.id,
        organization_id=org_id,
        resource_id=str(channel.id),
        new_value={"type": channel.channel_type, "name": channel.name},
        request=request,
    )
    await db.commit()
    return {"id": channel.id, "name": channel.name, "channel_type": channel.channel_type, "is_active": channel.is_active}


@router.get("/orgs/{org_id}/channels")
async def list_channels(org_id: int, user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await _require_org_access(db, org_id, user.id, write=False)
    result = await db.execute(
        select(NotificationChannel).where(NotificationChannel.organization_id == org_id).order_by(NotificationChannel.created_at.desc())
    )
    channels = result.scalars().all()
    return [
        {
            "id": c.id,
            "channel_type": c.channel_type,
            "name": c.name,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat(),
        }
        for c in channels
    ]


@router.post("/orgs/{org_id}/maintenance")
async def create_maintenance(org_id: int, req: MaintenanceRequest, request: Request, user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await _require_org_access(db, org_id, user.id, write=True)
    if req.ends_at <= req.starts_at:
        raise HTTPException(status_code=400, detail="ends_at must be after starts_at")

    mw = MaintenanceWindow(
        organization_id=org_id,
        title=req.title.strip(),
        starts_at=req.starts_at,
        ends_at=req.ends_at,
        created_by_user_id=user.id,
    )
    db.add(mw)
    await db.flush()
    await write_audit_log(
        db,
        action="maintenance_window_created",
        resource_type="maintenance_window",
        actor_user_id=user.id,
        organization_id=org_id,
        resource_id=str(mw.id),
        new_value={"starts_at": req.starts_at.isoformat(), "ends_at": req.ends_at.isoformat(), "title": req.title},
        request=request,
    )
    await db.commit()
    return {"id": mw.id, "title": mw.title, "starts_at": mw.starts_at.isoformat(), "ends_at": mw.ends_at.isoformat()}


@router.get("/orgs/{org_id}/maintenance")
async def list_maintenance(org_id: int, user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await _require_org_access(db, org_id, user.id, write=False)
    result = await db.execute(
        select(MaintenanceWindow)
        .where(MaintenanceWindow.organization_id == org_id)
        .order_by(MaintenanceWindow.starts_at.desc())
        .limit(100)
    )
    windows = result.scalars().all()
    return [
        {
            "id": w.id,
            "title": w.title,
            "starts_at": w.starts_at.isoformat(),
            "ends_at": w.ends_at.isoformat(),
        }
        for w in windows
    ]


@router.get("/orgs/{org_id}/slo-summary")
async def slo_summary(org_id: int, days: int = Query(default=30, ge=1, le=90), user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await _require_org_access(db, org_id, user.id, write=False)
    since = datetime.utcnow() - timedelta(days=days)

    member_users_result = await db.execute(select(OrganizationMember.user_id).where(OrganizationMember.organization_id == org_id))
    user_ids = [row[0] for row in member_users_result.all()]
    if not user_ids:
        return {"days": days, "services": [], "overall_uptime": 100.0}

    sites_result = await db.execute(select(Site).where(and_(Site.user_id.in_(user_ids), Site.is_active == True)))
    sites = sites_result.scalars().all()
    services = []
    all_checks: list[CheckLog] = []

    for s in sites:
        checks_result = await db.execute(
            select(CheckLog).where(and_(CheckLog.site_id == s.id, CheckLog.checked_at >= since)).order_by(CheckLog.checked_at.asc())
        )
        checks = checks_result.scalars().all()
        all_checks.extend(checks)
        services.append({
            "site_id": s.id,
            "name": s.name or s.url,
            "uptime": _uptime_percent(checks),
            "checks": len(checks),
        })

    return {
        "days": days,
        "services": services,
        "overall_uptime": _uptime_percent(all_checks),
        "metrics": metrics_snapshot(),
    }


@router.get("/orgs/{org_id}/slo-export.csv")
async def slo_export_csv(org_id: int, days: int = Query(default=30, ge=1, le=90), user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    data = await slo_summary(org_id, days=days, user=user, db=db)
    buff = StringIO()
    writer = csv.writer(buff)
    writer.writerow(["site_id", "name", "uptime", "checks", "days"])
    for svc in data["services"]:
        writer.writerow([svc["site_id"], svc["name"], svc["uptime"], svc["checks"], data["days"]])
    writer.writerow([])
    writer.writerow(["overall_uptime", data["overall_uptime"]])
    return PlainTextResponse(buff.getvalue(), media_type="text/csv")


@router.get("/sso/oidc/start")
async def oidc_start():
    if not settings.OIDC_AUTH_URL or not settings.OIDC_CLIENT_ID or not settings.OIDC_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="OIDC is not configured")
    # Minimal OIDC start endpoint (PKCE/state can be added in next iteration).
    url = (
        f"{settings.OIDC_AUTH_URL}?response_type=code"
        f"&client_id={settings.OIDC_CLIENT_ID}"
        f"&redirect_uri={settings.OIDC_REDIRECT_URI}"
        f"&scope=openid%20profile%20email"
    )
    return RedirectResponse(url=url)


@router.get("/metrics")
async def platform_metrics(user: User = Depends(get_current_active_user)):
    return metrics_snapshot()


@router.get("/scim/v2/Users")
async def scim_users(request: Request, token: str | None = Query(default=None), db: AsyncSession = Depends(get_db)):
    authz = request.headers.get("authorization", "")
    provided = token or (authz.replace("Bearer ", "") if authz.startswith("Bearer ") else None)
    if not settings.SCIM_BEARER_TOKEN or provided != settings.SCIM_BEARER_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid SCIM token")

    result = await db.execute(select(User))
    users = result.scalars().all()
    resources = []
    for u in users:
        resources.append(
            {
                "id": str(u.id),
                "userName": u.email,
                "active": bool(u.is_active),
                "emails": [{"value": u.email, "primary": True}],
            }
        )
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(resources),
        "itemsPerPage": len(resources),
        "startIndex": 1,
        "Resources": resources,
    }
