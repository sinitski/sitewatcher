import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.auth import get_current_active_user
from app.core.config import settings
from app.db.database import get_db
from app.models.payment import PaymentLog
from app.models.user import User
from app.services.telegram import send_telegram_message
from app.services.events import log_product_event

router = APIRouter(prefix="/billing", tags=["billing"])

PRICE_STARS = 500  # Telegram Stars for Pro (~$10)
PAYPAL_AMOUNT_USD = "9.99"  # PayPal order amount in USD (one-time payment)
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "").strip()
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
PAYPAL_SUCCESS_URL = os.getenv("PAYPAL_SUCCESS_URL", "").strip()
PAYPAL_CANCEL_URL = os.getenv("PAYPAL_CANCEL_URL", "").strip()
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox").strip().lower()


def _paypal_base_url() -> str:
    return "https://api-m.paypal.com" if PAYPAL_MODE == "live" else "https://api-m.sandbox.paypal.com"


async def _paypal_access_token() -> str:
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "Card payments are temporarily unavailable. "
                "Ask the site owner to configure PayPal (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)."
            ),
        )

    url = f"{_paypal_base_url()}/v1/oauth2/token"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"PayPal auth error: {response.text}")

    token = response.json().get("access_token")
    if not token:
        raise HTTPException(status_code=502, detail="PayPal auth error: no access_token in response")
    return token


async def _paypal_api_post(path: str, payload: dict) -> dict:
    token = await _paypal_access_token()
    url = f"{_paypal_base_url()}/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"PayPal error: {response.text}")
    return response.json()


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


# ── PayPal Checkout ──────────────────────────────────────────────────────────


@router.post("/paypal-checkout")
async def create_paypal_checkout(
    user: User = Depends(get_current_active_user),
):
    """Create a PayPal order for Pro and return approval URL."""
    if user.is_paid:
        raise HTTPException(status_code=400, detail="Already Pro")

    success_url = PAYPAL_SUCCESS_URL or f"{settings.FRONTEND_URL}/upgrade?paypal=success"
    cancel_url = PAYPAL_CANCEL_URL or f"{settings.FRONTEND_URL}/upgrade?paypal=cancel"

    order = await _paypal_api_post(
        "/v2/checkout/orders",
        {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": f"sitewatcher-pro-{user.id}",
                    "custom_id": str(user.id),
                    "description": "SiteWatcher Pro",
                    "amount": {
                        "currency_code": "USD",
                        "value": PAYPAL_AMOUNT_USD,
                    },
                }
            ],
            "application_context": {
                "brand_name": "SiteWatcher",
                "user_action": "PAY_NOW",
                "return_url": success_url,
                "cancel_url": cancel_url,
            },
        },
    )

    approve_url = ""
    for link in order.get("links", []):
        if link.get("rel") == "approve":
            approve_url = link.get("href") or ""
            break

    if not approve_url:
        raise HTTPException(status_code=502, detail="PayPal error: no approve URL returned")

    return {"ok": True, "url": approve_url, "id": order.get("id")}


class PayPalCaptureRequest(BaseModel):
    order_id: str


@router.post("/paypal-capture")
async def paypal_capture(req: PayPalCaptureRequest, user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Capture approved PayPal order and activate Pro."""
    if user.is_paid:
        return {"ok": True, "is_paid": True}

    order = await _paypal_api_post(f"/v2/checkout/orders/{req.order_id}/capture", {})
    status_value = (order.get("status") or "").upper()
    if status_value != "COMPLETED":
        raise HTTPException(status_code=400, detail=f"PayPal order is not completed: {status_value or 'unknown'}")

    purchase_units = order.get("purchase_units") or []
    first_unit = purchase_units[0] if purchase_units else {}
    custom_id = str(first_unit.get("custom_id") or "")
    if custom_id and custom_id != str(user.id):
        raise HTTPException(status_code=403, detail="PayPal order does not belong to current user")

    captures = (((first_unit.get("payments") or {}).get("captures")) or [])
    capture = captures[0] if captures else {}
    amount_obj = capture.get("amount") or first_unit.get("amount") or {}
    amount_value = amount_obj.get("value", PAYPAL_AMOUNT_USD)
    currency = amount_obj.get("currency_code", "USD")

    user.is_paid = True
    payment = PaymentLog(
        user_id=user.id,
        amount=float(amount_value),
        currency=currency,
        payment_method="paypal",
        external_id=capture.get("id") or req.order_id,
        comment="PayPal Checkout payment",
        status="success",
    )
    db.add(payment)
    await db.commit()
    await log_product_event(db, "upgraded_to_pro", user.id, {"source": "paypal", "order_id": req.order_id})
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

    return {"ok": True, "is_paid": True}


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
        await log_product_event(db, "upgraded_to_pro", user.id, {"source": "admin_activate"})
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
    await log_product_event(db, "upgraded_to_pro", user.id, {"source": data.get("method", "manual")})
    await db.commit()

    return {
        "ok": True,
        "is_paid": True,
        "message": f"Pro activated and payment logged for {user_email}",
    }