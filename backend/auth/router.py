"""
Slancio Crypto Algo Treding Engine — Auth Router (Full OTP Flow)
=================================================================
Handles registration with Indian mobile+email OTP verification,
login, forgot password, and password reset via OTP.
"""

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.auth import security
from database.connection import get_db_session
from database.models import User, OTPRecord
from core.otp_service import generate_otp, send_email_otp, send_sms_otp

router = APIRouter(prefix="/api/auth", tags=["auth"])

OTP_EXPIRY_MINUTES = 10


# ─── Schemas ───
class UserCreate(BaseModel):
    username: str
    email: EmailStr
    mobile_number: str   # Indian mobile: 10 digits or +91XXXXXXXXXX
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class OTPRequest(BaseModel):
    identifier: str   # email or mobile
    otp_type: str     # 'email_verify' | 'mobile_verify' | 'forgot_password'


class OTPVerify(BaseModel):
    identifier: str
    otp_code: str
    otp_type: str


class PasswordReset(BaseModel):
    identifier: str
    otp_code: str
    new_password: str


def _normalize_mobile(mobile: str) -> str:
    """Normalize Indian mobile number to 10 digits."""
    mobile = re.sub(r'\D', '', mobile)
    if mobile.startswith("91") and len(mobile) == 12:
        mobile = mobile[2:]
    if len(mobile) != 10:
        raise HTTPException(status_code=400, detail="Invalid Indian mobile number. Must be 10 digits.")
    return mobile


# ─── REGISTRATION ───
@router.post("/register")
async def register(user: UserCreate, db: AsyncSession = Depends(get_db_session)):
    """Register a new user with email + Indian mobile number."""

    mobile = _normalize_mobile(user.mobile_number)

    # Check if email, username, or mobile already exists
    stmt = select(User).where(
        (User.username == user.username) |
        (User.email == user.email) |
        (User.mobile_number == mobile)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username, email, or mobile number already registered.")

    # Determine role — first user is always admin
    count_result = await db.execute(select(User))
    role = "admin" if len(count_result.scalars().all()) == 0 else "user"

    new_user = User(
        username=user.username,
        email=user.email,
        mobile_number=mobile,
        password_hash=security.get_password_hash(user.password),
        role=role,
        is_email_verified=False,
        is_mobile_verified=True,  # Mobile OTP verification bypassed as requested
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Auto-send OTP for email only
    email_otp = generate_otp()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    db.add(OTPRecord(user_id=new_user.id, otp_code=email_otp, otp_type="email_verify", target=user.email, expires_at=expiry))
    await db.commit()

    await send_email_otp(user.email, email_otp, "email_verify")

    return {
        "status": "success",
        "message": "Registered! OTP sent to your email. Please verify.",
        "user_id": new_user.id,
        "role": role
    }


# ─── RESEND OTP ───
@router.post("/otp/send")
async def send_otp(data: OTPRequest, db: AsyncSession = Depends(get_db_session)):
    """Send or resend OTP to email or mobile."""
    is_email = "@" in data.identifier

    if is_email:
        stmt = select(User).where(User.email == data.identifier)
    else:
        mobile = _normalize_mobile(data.identifier)
        stmt = select(User).where(User.mobile_number == mobile)

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found with this identifier.")

    otp = generate_otp()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    db.add(OTPRecord(
        user_id=user.id,
        otp_code=otp,
        otp_type=data.otp_type,
        target=data.identifier,
        expires_at=expiry
    ))
    await db.commit()

    if is_email:
        await send_email_otp(data.identifier, otp, data.otp_type)
    else:
        await send_sms_otp(data.identifier, otp)

    return {"status": "success", "message": "OTP sent successfully."}


# ─── VERIFY OTP ───
@router.post("/otp/verify")
async def verify_otp(data: OTPVerify, db: AsyncSession = Depends(get_db_session)):
    """Verify OTP for email or mobile."""
    is_email = "@" in data.identifier

    if is_email:
        stmt = select(User).where(User.email == data.identifier)
    else:
        mobile = _normalize_mobile(data.identifier)
        stmt = select(User).where(User.mobile_number == mobile)

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # Fetch latest valid OTP
    now = datetime.now(timezone.utc)
    otp_stmt = select(OTPRecord).where(
        OTPRecord.user_id == user.id,
        OTPRecord.otp_type == data.otp_type,
        OTPRecord.is_used == False,
        OTPRecord.expires_at > now,
        OTPRecord.otp_code == data.otp_code
    ).order_by(OTPRecord.created_at.desc())

    otp_result = await db.execute(otp_stmt)
    otp_record = otp_result.scalar_one_or_none()

    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    otp_record.is_used = True

    if data.otp_type == "email_verify":
        user.is_email_verified = True
    elif data.otp_type == "mobile_verify":
        user.is_mobile_verified = True

    await db.commit()
    return {"status": "success", "message": "Verification successful!"}


# ─── FORGOT PASSWORD — Send OTP ───
@router.post("/forgot-password")
async def forgot_password(data: OTPRequest, db: AsyncSession = Depends(get_db_session)):
    """Initiate password reset by sending OTP to email or mobile."""
    is_email = "@" in data.identifier

    if is_email:
        stmt = select(User).where(User.email == data.identifier)
    else:
        mobile = _normalize_mobile(data.identifier)
        stmt = select(User).where(User.mobile_number == mobile)

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this email or mobile.")

    otp = generate_otp()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)
    db.add(OTPRecord(
        user_id=user.id,
        otp_code=otp,
        otp_type="forgot_password",
        target=data.identifier,
        expires_at=expiry
    ))
    await db.commit()

    if is_email:
        await send_email_otp(data.identifier, otp, "forgot_password")
    else:
        await send_sms_otp(data.identifier, otp)

    return {"status": "success", "message": f"OTP sent to {data.identifier}"}


# ─── FORGOT PASSWORD — Reset ───
@router.post("/reset-password")
async def reset_password(data: PasswordReset, db: AsyncSession = Depends(get_db_session)):
    """Reset password after OTP verification."""
    is_email = "@" in data.identifier

    if is_email:
        stmt = select(User).where(User.email == data.identifier)
    else:
        mobile = _normalize_mobile(data.identifier)
        stmt = select(User).where(User.mobile_number == mobile)

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    now = datetime.now(timezone.utc)
    otp_stmt = select(OTPRecord).where(
        OTPRecord.user_id == user.id,
        OTPRecord.otp_type == "forgot_password",
        OTPRecord.is_used == False,
        OTPRecord.expires_at > now,
        OTPRecord.otp_code == data.otp_code
    ).order_by(OTPRecord.created_at.desc())

    otp_result = await db.execute(otp_stmt)
    otp_record = otp_result.scalar_one_or_none()

    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    otp_record.is_used = True
    user.password_hash = security.get_password_hash(data.new_password)
    await db.commit()

    return {"status": "success", "message": "Password reset successfully! Please login."}


# ─── LOGIN ───
@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db_session)
):
    """Login with username and password."""
    stmt = select(User).where(User.username == form_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = security.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}
