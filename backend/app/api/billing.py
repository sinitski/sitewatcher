import hashlib
import hmac
import json
import os
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_active_user
from app.core.config import settings
from app.db.database import get_db
from app.models.payment import PaymentLog
from app.models.user import User
from app.services.telegram import send_telegram_message

router = APIRouter(prefix="/billing", tags=["billing"])

PRICE_STARS = 500  # Telegram Stars for Pro (~$10)
STRIPE_AMOUNT_USD = 999  # Stripe Checkout price in USD (one-time payment)
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_SUCCESS_URL = os.getenv("STRIPE_SUCCESS_URL", "").strip()
STRIPE_CANCEL_URL = os.getenv("STRIPE_CANCEL_URL", "").strip()


async def _stripe_post(path: str, data: dict) -> dict:
    if not STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Card payments are temporarily unavailable. Ask the site owner to configure Stripe (STRIPE_SECRET_KEY).",
        )

    url = f"https://api.stripe.com/v1/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
            data=data,
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Stripe error: {response.text}")
    return response.json()


def _verify_stripe_signature(payload: bytes, signature_header: str) -> bool:
    if not STRIPE_WEBHOOK_SECRET:
        return False

    parts: dict[str, list[str]] = {}
    for item in signature_header.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            parts.setdefault(key, []).append(value)

    timestamp = parts.get("t", [None])[0]
    signatures = parts.get("v1", [])
    if not timestamp or not signatures:
        return False

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - timestamp_int) > 300:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


# ── Telegram Stars ───────────────────────────────────────────────────────────


@router.post("/send-invoice")
async def send_stars_invoice(
    user: User = Depends(get_current_active_user),
):
    """Send a Telegram Stars invoice to the user's chat."""
    if user.is_paid:
        raise HTTPException(status_code=400, detail="Already Pro")
    if not user.telegram_chat_id:
        raise HTTPException(status_code=400, detail="Connect Telegram first")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendInvoice",
            json={
                "chat_id": user.telegram_chat_id,
                "title": "SiteWatcher Pro",
                "description": "50 sites · checks every 1 min · content monitoring",
                "payload": user.upgrade_token,
                "currency": "XTR",
                "prices": [{"label": "Pro Plan", "amount": PRICE_STARS}],
            },
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Telegram error: {response.text}")

    return {"ok": True, "message": "Invoice sent to Telegram"}


# ── Stripe Checkout ──────────────────────────────────────────────────────────


@router.post("/stripe-checkout")
async def create_stripe_checkout(
    user: User = Depends(get_current_active_user),
):
    """Create a Stripe Checkout session for Pro."""
    if user.is_paid:
        raise HTTPException(status_code=400, detail="Already Pro")

    success_url = STRIPE_SUCCESS_URL or f"{settings.FRONTEND_URL}/upgrade?stripe=success"
    cancel_url = STRIPE_CANCEL_URL or f"{settings.FRONTEND_URL}/upgrade?stripe=cancel"

    session = await _stripe_post(
        "checkout/sessions",
        {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "customer_email": user.email,
            "client_reference_id": str(user.id),
            "metadata[user_id]": str(user.id),
            "metadata[email]": user.email,
            "metadata[upgrade_token]": user.upgrade_token,
            "line_items[0][quantity]": 1,
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][product_data][name]": "SiteWatcher Pro",
            "line_items[0][price_data][product_data][description]": "50 sites, 1 minute checks, content monitoring, AI insights",
            "line_items[0][price_data][unit_amount]": STRIPE_AMOUNT_USD,
        },
    )

    return {"ok": True, "url": session["url"], "id": session["id"]}


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle Stripe webhook events and activate Pro on successful payments."""
    raw_body = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    if not _verify_stripe_signature(raw_body, signature):
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    event = json.loads(raw_body.decode("utf-8"))
    if event.get("type") != "checkout.session.completed":
        return {"ok": True}

    session = event.get("data", {}).get("object", {})
    if session.get("payment_status") != "paid":
        return {"ok": True}

    metadata = session.get("metadata", {}) or {}
    user_id = metadata.get("user_id")
    email = metadata.get("email")

    user = None
    if user_id:
        user = await db.get(User, int(user_id))
    if not user and email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

    if not user:
        return {"ok": True}

    if not user.is_paid:
        user.is_paid = True

    payment = PaymentLog(
        user_id=user.id,
        amount=float(session.get("amount_total", STRIPE_AMOUNT_USD)) / 100.0,
        currency=(session.get("currency") or "usd").upper(),
        payment_method="stripe",
        external_id=session.get("id"),
        comment="Stripe Checkout payment",
        status="success",
    )
    db.add(payment)
    await db.commit()

    if user.telegram_chat_id:
        await send_telegram_message(
            user.telegram_chat_id,
            "🎉 <b>Pro activated!</b>\n\n"
            "You now have access to:\n"
            "• Up to 50 monitored sites\n"
            "• Checks every 1 minute\n"
            "• Content change monitoring\n"
            "• AI insights\n\n"
            "Thank you for your payment! 🚀",
        )

    return {"ok": True}


# ── Admin activation ─────────────────────────────────────────────────────────


@router.post("/admin/activate/{user_email}")
async def admin_activate(
    user_email: str,
    secret: str,
    db: AsyncSession = Depends(get_db),
):
    """Manually activate Pro for a user."""
    if not ADMIN_SECRET or secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(select(User).where(User.email == user_email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_paid:
        user.is_paid = True
        await db.commit()

        if user.telegram_chat_id:
            await send_telegram_message(
                user.telegram_chat_id,
                "🎉 <b>Pro activated!</b>\n\n"
                "You now have access to:\n"
                "• Up to 50 monitored sites\n"
                "• Checks every 1 minute\n"
                "• Content change monitoring\n\n"
                "Thank you! 🚀",
            )

    return {"ok": True, "is_paid": True, "email": user_email}


@router.post("/admin/deactivate/{user_email}")
async def admin_deactivate(
    user_email: str,
    secret: str,
    db: AsyncSession = Depends(get_db),
):
    """Deactivate Pro for a user."""
    if not ADMIN_SECRET or secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = await db.execute(select(User).where(User.email == user_email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_paid = False
    await db.commit()
    return {"ok": True, "is_paid": False, "email": user_email}


# ── Status ───────────────────────────────────────────────────────────────────


@router.get("/status")
async def billing_status(user: User = Depends(get_current_active_user)):
    return {
        "is_paid": user.is_paid,
        "upgrade_token": user.upgrade_token,
    }


# ── Payment logging ──────────────────────────────────────────────────────────


@router.post("/log-payment")
async def log_payment(
    data: dict,
    secret: str,
    db: AsyncSession = Depends(get_db),
):
    """Store a manual payment log after a payment provider confirms the order."""
    if not ADMIN_SECRET or secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    user_email = data.get("email")
    if not user_email:
        raise HTTPException(status_code=400, detail="email is required")

    result = await db.execute(select(User).where(User.email == user_email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.is_paid:
        user.is_paid = True

    payment = PaymentLog(
        user_id=user.id,
        amount=data.get("amount", 900),
        payment_method=data.get("method", "manual"),
        external_id=data.get("order_id"),
        comment=data.get("comment"),
        status="success",
    )
    db.add(payment)
    await db.commit()

    return {
        "ok": True,
        "is_paid": True,
        "message": f"Pro activated and payment logged for {user_email}",
    }