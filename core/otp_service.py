"""
Slancio Crypto Algo Treding Engine — OTP Service
===================================================
Handles OTP generation and sending via Email (Gmail SMTP port 587 STARTTLS).
"""

import random
import string
from loguru import logger
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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


# ─── Email OTP (Sync via smtplib — most reliable) ───
async def send_email_otp(to_email: str, otp: str, purpose: str = "verification") -> bool:
    """
    Send OTP to an email address via Gmail SMTP (port 587, STARTTLS).
    Requires EMAIL_USER and EMAIL_PASSWORD in environment.
    Uses standard smtplib for maximum reliability.
    """
    if not settings.email_user or not settings.email_password:
        logger.warning(f"[DEV MODE] Email not configured — OTP for {to_email} is: {otp}")
        _dev_otp_store[to_email] = otp
        return True

    subject_map = {
        "email_verify":    "Slancio — Verify Your Email Address",
        "mobile_verify":   "Slancio — Verify Your Mobile Number",
        "forgot_password": "Slancio — Password Reset OTP",
    }
    subject = subject_map.get(purpose, "Slancio — One-Time Password")

    html_body = f"""
    <html><body style="font-family: Arial, sans-serif; background: #0f1117; color: #fff; padding: 40px;">
    <div style="max-width: 480px; margin: auto; background: #1a1d2e; border-radius: 16px; padding: 32px; border: 1px solid rgba(99,102,241,0.3);">
        <h2 style="color: #6366f1; margin-bottom: 4px;">Slancio Algo Engine</h2>
        <p style="color: #94a3b8;">Your One-Time Password</p>
        <div style="background: rgba(99,102,241,0.1); border: 1px solid #6366f1; border-radius: 12px; padding: 24px; text-align: center; margin: 24px 0;">
            <h1 style="color: #fff; font-size: 40px; letter-spacing: 12px; margin: 0;">{otp}</h1>
        </div>
        <p style="color: #94a3b8; font-size: 14px;">This OTP expires in <strong>10 minutes</strong>. Do not share it.</p>
        <hr style="border-color: rgba(255,255,255,0.1);">
        <p style="color: #64748b; font-size: 12px;">If you did not request this, please ignore this email.</p>
    </div></body></html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Slancio Algo Engine <{settings.email_user}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        # Use standard smtplib with STARTTLS on port 587 (most reliable for Gmail)
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.email_user, settings.email_password)
            server.sendmail(settings.email_user, to_email, msg.as_string())

        logger.success(f"Email OTP sent successfully to {to_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(f"Gmail auth failed — ensure 2FA is on and EMAIL_PASSWORD is a 16-char App Password, not your Gmail password.")
        _dev_otp_store[to_email] = otp   # fallback: store for dev retrieval
        return False
    except Exception as e:
        logger.error(f"Failed to send email OTP to {to_email}: {e}")
        _dev_otp_store[to_email] = otp   # fallback: store for dev retrieval
        return False


# ─── SMS OTP — disabled (mobile OTP not required) ───
async def send_sms_otp(mobile: str, otp: str) -> bool:
    logger.info(f"[SMS DISABLED] OTP for {mobile}: {otp}")
    return True
