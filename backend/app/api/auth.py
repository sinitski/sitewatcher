from datetime import datetime, timedelta
import re

import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr, Field
from app.db.database import get_db
from app.models.user import User
from app.services.auth import (
    hash_password, authenticate_user, create_access_token,
    get_user_by_email, get_current_user, generate_upgrade_token,
    generate_unique_referral_code, get_user_by_referral_code, get_max_sites_for_user
)
from app.core.config import settings
from app.services.telegram import send_telegram_message
from app.services.email import normalize_email_list, send_verification_email, split_email_list

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class VerificationEmailRequest(BaseModel):
    email: EmailStr


class ApplyReferralRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class NotificationSettingsRequest(BaseModel):
    email_alerts_enabled: bool = False
    alert_emails: list[EmailStr] = Field(default_factory=list)


async def get_current_active_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_current_user(credentials.credentials, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Please confirm your email address before signing in")
    return user

@router.post("/me/test-alert")
async def test_alert(user: User = Depends(get_current_active_user)):
    if not user.telegram_chat_id:
        raise HTTPException(status_code=400, detail="No telegram_chat_id set")
    result = await send_telegram_message(
        user.telegram_chat_id,
        "🧪 <b>Test alert from SiteWatcher!</b>\nAlerts are working correctly."
    )
    return {"sent": result}

def _create_email_verification_token() -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=1)
    return token, expires_at


def _validate_password_complexity(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if not re.search(r"[A-Za-z]", password):
        return "Password must include at least one letter"
    if not re.search(r"\d", password):
        return "Password must include at least one digit"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include at least one special character"
    return None


def _build_verification_url(request: Request, token: str) -> str:
    base = settings.BACKEND_URL.rstrip("/")
    return f"{base}/api/auth/verify-email?token={token}"


@router.post("/register")
async def register(req: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    existing = await get_user_by_email(db, req.email)
    if existing:
        if existing.email_verified:
            raise HTTPException(status_code=400, detail="Email already registered")

        token, expires_at = _create_email_verification_token()
        existing.email_verification_token = token
        existing.email_verification_expires_at = expires_at
        await db.commit()

        verification_url = _build_verification_url(request, token)
        sent = await send_verification_email(existing.email, verification_url)
        if not sent:
            from app.services.email import _config_error, get_last_email_error
            transport_error = get_last_email_error()
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Could not send confirmation email: {_config_error()}"
                    f". Transport error: {transport_error or 'unknown'}"
                    ". Check Gmail API OAuth credentials and that Gmail API is enabled in Google Cloud."
                ),
            )

        return {
            "ok": True,
            "message": "Account already exists but email is not confirmed. We sent you a new confirmation link.",
        }

    password_error = _validate_password_complexity(req.password)
    if password_error:
        raise HTTPException(status_code=400, detail=password_error)

    verification_token, verification_expires_at = _create_email_verification_token()

    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        upgrade_token=generate_upgrade_token(),
        referral_code=await generate_unique_referral_code(db),
        email_verified=False,
        email_verification_token=verification_token,
        email_verification_expires_at=verification_expires_at,
    )
    db.add(user)
    await db.flush()

    verification_url = _build_verification_url(request, verification_token)
    sent = await send_verification_email(user.email, verification_url)
    if not sent:
        await db.rollback()
        from app.services.email import _config_error, get_last_email_error
        transport_error = get_last_email_error()
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not send confirmation email: {_config_error()}"
                f". Transport error: {transport_error or 'unknown'}"
                ". Check Gmail API OAuth credentials and that Gmail API is enabled in Google Cloud."
            ),
        )

    await db.commit()
    return {"ok": True, "message": "Check your inbox to confirm your email address before signing in."}


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Please confirm your email address before signing in")

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)

@router.get("/me")
async def me(user: User = Depends(get_current_active_user)):
    max_sites = get_max_sites_for_user(user)
    return {
        "id": user.id,
        "email": user.email,
        "is_paid": user.is_paid,
        "email_verified": user.email_verified,
        "telegram_chat_id": user.telegram_chat_id,
        "telegram_username": user.telegram_username,
        "upgrade_token": user.upgrade_token,
        "referral": {
            "code": user.referral_code,
            "referred_by_user_id": user.referred_by_user_id,
            "bonus_sites": user.referral_bonus_sites or 0,
        },
        "notifications": {
            "email_alerts_enabled": user.email_alerts_enabled,
            "alert_emails": split_email_list(user.alert_emails),
        },
        "limits": {
            "max_sites": max_sites,
            "min_interval": settings.PAID_TIER_MIN_INTERVAL if user.is_paid else settings.FREE_TIER_MIN_INTERVAL,
        }
    }


@router.get("/verify-email", name="verify_email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email_verification_token == token))
    user = result.scalar_one_or_none()
    login_url = f"{settings.FRONTEND_URL.rstrip('/')}/#/login"

    if not user:
        return RedirectResponse(url=f"{login_url}?verified=invalid", status_code=302)

    if user.email_verification_expires_at and user.email_verification_expires_at < datetime.utcnow():
        return RedirectResponse(url=f"{login_url}?verified=expired", status_code=302)

    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_expires_at = None
    await db.commit()
    return RedirectResponse(url=f"{login_url}?verified=success", status_code=302)


@router.post("/verification-email")
async def send_verification_email_again(req: VerificationEmailRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user:
        return {"ok": True, "message": "If the email exists, we sent a new confirmation link."}
    if user.email_verified:
        return {"ok": True, "message": "Email is already confirmed."}

    token, expires_at = _create_email_verification_token()
    user.email_verification_token = token
    user.email_verification_expires_at = expires_at
    await db.commit()

    verification_url = _build_verification_url(request, token)
    sent = await send_verification_email(user.email, verification_url)
    if not sent:
        from app.services.email import _config_error, get_last_email_error
        transport_error = get_last_email_error()
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not send confirmation email: {_config_error()}"
                f". Transport error: {transport_error or 'unknown'}"
                ". Check Gmail API OAuth credentials and that Gmail API is enabled in Google Cloud."
            ),
        )
    return {"ok": True, "message": "If the email exists, we sent a new confirmation link."}


@router.post("/me/apply-referral")
async def apply_referral(
    req: ApplyReferralRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    code = req.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Referral code is required")

    if user.referred_by_user_id is not None:
        raise HTTPException(status_code=400, detail="Referral code already used")

    if user.referral_code and code == user.referral_code:
        raise HTTPException(status_code=400, detail="You cannot use your own referral code")

    inviter = await get_user_by_referral_code(db, code)
    if not inviter:
        raise HTTPException(status_code=404, detail="Referral code not found")
    if inviter.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot use your own referral code")

    user.referred_by_user_id = inviter.id
    user.referral_bonus_sites = (user.referral_bonus_sites or 0) + 1
    inviter.referral_bonus_sites = (inviter.referral_bonus_sites or 0) + 1

    await db.commit()

    return {
        "ok": True,
        "message": "Referral applied: both users received +1 site limit",
        "limits": {
            "max_sites": get_max_sites_for_user(user),
            "min_interval": settings.PAID_TIER_MIN_INTERVAL if user.is_paid else settings.FREE_TIER_MIN_INTERVAL,
        },
    }

class TelegramRequest(BaseModel):
    chat_id: str


@router.patch("/me/notifications")
async def update_notifications(
    req: NotificationSettingsRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    user.email_alerts_enabled = req.email_alerts_enabled
    user.alert_emails = ",".join(normalize_email_list([str(email) for email in req.alert_emails])) or None
    await db.commit()
    return {
        "ok": True,
        "notifications": {
            "email_alerts_enabled": user.email_alerts_enabled,
            "alert_emails": split_email_list(user.alert_emails),
        },
    }

@router.patch("/me/telegram")
async def set_telegram(
    req: TelegramRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    user.telegram_chat_id = req.chat_id
    await db.commit()
    return {"telegram_chat_id": user.telegram_chat_id}