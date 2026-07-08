"""
Slancio Crypto Algo Treding Engine — Database Models
=======================================
SQLAlchemy ORM models for Users, API Keys, Trade Logs, and OTP Records.
"""

from datetime import datetime, timezone
import uuid
from typing import Optional, List

from sqlalchemy import String, Float, Integer, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    mobile_number: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="user")  # 'user' or 'admin'
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mobile_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    bot_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Position Sizing & Risk Settings (per-user override)
    position_size_pct: Mapped[float] = mapped_column(Float, default=0.02)   # 2% default
    max_leverage: Mapped[int] = mapped_column(Integer, default=10)
    stop_loss_points: Mapped[float] = mapped_column(Float, default=400.0)
    take_profit_points: Mapped[float] = mapped_column(Float, default=800.0)  # 2:1 R:R default
    margin_type: Mapped[str] = mapped_column(String, default="isolated")    # 'isolated' or 'cross'
    trading_timeframe: Mapped[str] = mapped_column(String, default="1h")     # '1m','5m','15m','1h','4h'
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    api_keys: Mapped[List["ApiKey"]] = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    trade_logs: Mapped[List["TradeLog"]] = relationship("TradeLog", back_populates="user", cascade="all, delete-orphan")
    settings: Mapped["UserSettings"] = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    otp_records: Mapped[List["OTPRecord"]] = relationship("OTPRecord", back_populates="user", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"))
    
    # Store these encrypted!
    encrypted_api_key: Mapped[str] = mapped_column(String)
    encrypted_api_secret: Mapped[str] = mapped_column(String)
    
    exchange: Mapped[str] = mapped_column(String, default="delta_india")
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="api_keys")


class TradeLog(Base):
    __tablename__ = "trade_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    
    symbol: Mapped[str] = mapped_column(String, index=True)
    side: Mapped[str] = mapped_column(String)  # 'short' or 'long'
    status: Mapped[str] = mapped_column(String, default="open")  # 'open', 'closed', 'cancelled'
    
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit_target: Mapped[float] = mapped_column(Float)
    
    quantity: Mapped[int] = mapped_column(Integer)
    leverage: Mapped[int] = mapped_column(Integer)
    
    pnl_usdt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pnl_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    entry_order_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    exit_order_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # JSON metadata for storing strategy specifics (EMA values at entry time, etc.)
    strategy_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="trade_logs")


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    
    max_leverage: Mapped[int] = mapped_column(Integer, default=10)
    max_position_pct: Mapped[float] = mapped_column(Float, default=0.02)
    
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="settings")


class SystemState(Base):
    """Global system configurations for admin control"""
    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    global_kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    engine_status: Mapped[str] = mapped_column(String, default="running")
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class OTPRecord(Base):
    """Temporary OTP storage for email/mobile verification and password reset."""
    __tablename__ = "otp_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    otp_code: Mapped[str] = mapped_column(String)           # 6-digit OTP
    otp_type: Mapped[str] = mapped_column(String)           # 'email_verify' | 'mobile_verify' | 'forgot_password'
    target: Mapped[str] = mapped_column(String)              # The email or mobile it was sent to
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="otp_records")
