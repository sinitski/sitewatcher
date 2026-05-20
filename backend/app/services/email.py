import logging
import re
import base64
from email.message import EmailMessage
from typing import Iterable

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
GMAIL_FROM_NAME = "SiteWatcher"
_LAST_EMAIL_ERROR: str | None = None


def _set_last_email_error(value: str | None) -> None:
    global _LAST_EMAIL_ERROR
    _LAST_EMAIL_ERROR = value


def get_last_email_error() -> str | None:
    return _LAST_EMAIL_ERROR


def _is_gmail_api_configured() -> bool:
    return bool(
        settings.GMAIL_CLIENT_ID
        and settings.GMAIL_CLIENT_SECRET
        and settings.GMAIL_REFRESH_TOKEN
        and settings.GMAIL_SENDER_EMAIL
    )


def _is_configured() -> bool:
    return _is_gmail_api_configured()


def _config_error() -> str:
    missing_gmail: list[str] = []
    if not settings.GMAIL_CLIENT_ID:
        missing_gmail.append("GMAIL_CLIENT_ID")
    if not settings.GMAIL_CLIENT_SECRET:
        missing_gmail.append("GMAIL_CLIENT_SECRET")
    if not settings.GMAIL_REFRESH_TOKEN:
        missing_gmail.append("GMAIL_REFRESH_TOKEN")
    if not settings.GMAIL_SENDER_EMAIL:
        missing_gmail.append("GMAIL_SENDER_EMAIL")

    if _is_gmail_api_configured():
        return "Email provider is configured but sending failed"

    return (
        "Set Gmail API credentials: GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET + GMAIL_REFRESH_TOKEN + GMAIL_SENDER_EMAIL "
        f"(missing: {', '.join(missing_gmail) or 'none'})"
    )


def _build_from_field(display_name: str | None, from_email: str) -> str:
    if display_name:
        return f"{display_name} <{from_email}>"
    return from_email


def _build_gmail_raw_message(to_email: str, subject: str, html_body: str, text_body: str | None) -> str:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _build_from_field(GMAIL_FROM_NAME, settings.GMAIL_SENDER_EMAIL)
    msg["To"] = to_email

    plain = text_body or "This message contains HTML content."
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")

    raw_bytes = msg.as_bytes()
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8")


async def _get_gmail_access_token() -> str:
    payload = {
        "client_id": settings.GMAIL_CLIENT_ID,
        "client_secret": settings.GMAIL_CLIENT_SECRET,
        "refresh_token": settings.GMAIL_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(GMAIL_TOKEN_URL, data=payload)

    if response.status_code != 200:
        raise RuntimeError(f"token exchange failed: {response.status_code} {response.text}")

    token = response.json().get("access_token")
    if not token:
        raise RuntimeError("token exchange failed: access_token missing")
    return token


async def _send_via_gmail_api(to_email: str, subject: str, html_body: str, text_body: str | None) -> bool:
    raw_message = _build_gmail_raw_message(to_email, subject, html_body, text_body)

    try:
        access_token = await _get_gmail_access_token()
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                GMAIL_SEND_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"raw": raw_message},
            )
        if response.status_code not in (200, 202):
            _set_last_email_error(f"gmail api send failed: {response.status_code} {response.text}")
            logger.error("Gmail API send failed: %s %s", response.status_code, response.text)
            return False
    except Exception as exc:
        _set_last_email_error(str(exc))
        logger.error("Gmail API send failed: %s", exc)
        return False

    _set_last_email_error(None)
    return True


def normalize_email_list(emails: Iterable[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    if not emails:
        return cleaned

    for item in emails:
        value = item.strip().lower()
        if not value or "@" not in value:
            continue
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def split_email_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[;,\n]", raw)
    return normalize_email_list(parts)


async def send_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    if not _is_configured():
        _set_last_email_error(None)
        logger.warning("Gmail API email skipped: %s", _config_error())
        return False

    if _is_gmail_api_configured():
        return await _send_via_gmail_api(to_email, subject, html_body, text_body)

    logger.warning("Email provider not configured: %s", _config_error())
    _set_last_email_error(None)
    return False


async def send_verification_email(to_email: str, verification_url: str) -> bool:
    subject = "Confirm your SiteWatcher account"
    html_body = (
        f"<p>Welcome to SiteWatcher.</p>"
        f"<p>Please confirm your email address by clicking this link:</p>"
        f"<p><a href=\"{verification_url}\">Confirm email</a></p>"
        f"<p>If you did not create this account, you can ignore this message.</p>"
    )
    text_body = (
        "Welcome to SiteWatcher.\n\n"
        f"Confirm your email here: {verification_url}\n\n"
        "If you did not create this account, you can ignore this message."
    )
    return await send_email(to_email, subject, html_body, text_body)


async def send_alert_email(to_email: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    return await send_email(to_email, subject, html_body, text_body)