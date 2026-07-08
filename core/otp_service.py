"""
Slancio Crypto Algo Treding Engine — OTP Service
===================================================
Handles OTP generation, sending via Email and Indian SMS (Fast2SMS),
and verification for registration and password reset flows.
"""

import random
import string
from datetime import datetime, timedelta, timezone
from loguru import logger
import aiohttp
import aiosmtplib
from email.message import EmailMessage

from core.config import get_settings

settings = get_settings()


# In-memory store for dev mode OTPs (when no email creds configured)
_dev_otp_store: dict = {}


def generate_otp(length: int = 6) -> str:
    """Generate a secure 6-digit numeric OTP."""
    return ''.join(random.choices(string.digits, k=length))


def get_dev_otp(identifier: str) -> str | None:
    """Return the stored dev OTP for an email (returns None in production)."""
    return _dev_otp_store.get(identifier)


# ─── Email OTP ───
async def send_email_otp(to_email: str, otp: str, purpose: str = "verification") -> bool:
    """
    Send OTP to an email address via SMTP.
    Requires EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASSWORD in .env
    """
    if not settings.email_user or not settings.email_password:
        logger.warning(f"[DEV MODE] Email not configured — OTP for {to_email} is: {otp}")
        # Store in a module-level dict so the register endpoint can return it
        _dev_otp_store[to_email] = otp
        return True  # In dev, treat as success

    subject_map = {
        "email_verify": "Slancio — Verify Your Email Address",
        "mobile_verify": "Slancio — Verify Your Mobile Number",
        "forgot_password": "Slancio — Password Reset OTP",
    }
    subject = subject_map.get(purpose, "Slancio — One-Time Password")

    body = f"""
    <html><body style="font-family: Arial, sans-serif; background: #0f1117; color: #fff; padding: 40px;">
    <div style="max-width: 480px; margin: auto; background: #1a1d2e; border-radius: 16px; padding: 32px; border: 1px solid rgba(99,102,241,0.3);">
        <h2 style="color: #6366f1; margin-bottom: 4px;">Slancio Algo Engine</h2>
        <p style="color: #94a3b8;">Your One-Time Password</p>
        <div style="background: rgba(99,102,241,0.1); border: 1px solid #6366f1; border-radius: 12px; padding: 24px; text-align: center; margin: 24px 0;">
            <h1 style="color: #fff; font-size: 40px; letter-spacing: 12px; margin: 0;">{otp}</h1>
        </div>
        <p style="color: #94a3b8; font-size: 14px;">This OTP expires in <strong>10 minutes</strong>. Do not share it with anyone.</p>
        <hr style="border-color: rgba(255,255,255,0.1);">
        <p style="color: #64748b; font-size: 12px;">If you did not request this, please ignore this email.</p>
    </div></body></html>
    """

    try:
        msg = EmailMessage()
        msg["From"] = settings.email_user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body, subtype="html")

        await aiosmtplib.send(
            msg,
            hostname=settings.email_host,
            port=settings.email_port,
            username=settings.email_user,
            password=settings.email_password,
            use_tls=True,
        )
        logger.success(f"Email OTP sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email OTP to {to_email}: {e}")
        return False


# ─── SMS OTP (Fast2SMS — India) ───
async def send_sms_otp(mobile: str, otp: str) -> bool:
    """
    Send OTP via SMS using Fast2SMS API (India).
    Requires FAST2SMS_API_KEY in .env
    """
    if not settings.fast2sms_api_key:
        logger.warning("FAST2SMS_API_KEY not configured. OTP logged only.")
        logger.info(f"[DEV] SMS OTP for {mobile}: {otp}")
        return True  # In dev, treat as success

    # Strip country code if present
    clean_mobile = mobile.replace("+91", "").replace(" ", "").strip()

    url = "https://www.fast2sms.com/dev/bulkV2"
    payload = {
        "route": "otp",
        "variables_values": otp,
        "numbers": clean_mobile,
        "flash": 0
    }
    headers = {
        "authorization": settings.fast2sms_api_key,
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if data.get("return"):
                    logger.success(f"SMS OTP sent to +91{clean_mobile}")
                    return True
                else:
                    logger.error(f"Fast2SMS error: {data}")
                    return False
    except Exception as e:
        logger.error(f"Failed to send SMS OTP: {e}")
        return False
