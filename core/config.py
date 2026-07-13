"""
Slancio Crypto Algo Treding Engine — Global Configuration
=============================================
Centralized configuration management using Pydantic Settings.
All values are loaded from environment variables / .env file.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings
from pydantic import Field


# ── Project Root ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ExchangeRegion(str, Enum):
    """Supported Delta Exchange regions."""
    GLOBAL = "global"
    INDIA = "india"


class AppEnvironment(str, Enum):
    """Application environment modes."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """
    Application-wide settings loaded from environment variables.
    
    Usage:
        from core.config import get_settings
        settings = get_settings()
        print(settings.delta_api_key)
    """

    # ── Delta Exchange API ──
    delta_api_key: str = Field(default="", description="Delta Exchange API Key")
    delta_api_secret: str = Field(default="", description="Delta Exchange API Secret")
    delta_exchange_region: ExchangeRegion = Field(
        default=ExchangeRegion.INDIA,
        description="Delta Exchange region: 'global' or 'india'"
    )

    # ── Trading Configuration ──
    trading_symbol: str = Field(default="BTCUSD", description="Trading pair symbol")
    trading_timeframe: str = Field(default="1h", description="Candle timeframe")
    max_leverage: int = Field(default=10, ge=1, le=20, description="Maximum leverage (1-20x)")
    max_position_pct: float = Field(
        default=0.02, ge=0.001, le=0.10,
        description="Max position size as fraction of capital (0.02 = 2%)"
    )
    stop_loss_points: float = Field(
        default=600.0, ge=50, le=2000,
        description="Stop loss distance in points from entry"
    )
    dry_run: bool = Field(
        default=True, 
        description="If True, bot will log trades but won't send actual orders to the exchange."
    )

    # ── EMA Strategy Parameters ──
    ema_period: int = Field(default=7, ge=2, le=50, description="EMA period for High/Low")
    min_distance_from_ema_low: float = Field(
        default=400.0, ge=50,
        description="Minimum points Close must be above EMA 7 Low"
    )

    # ── Database ──
    database_url: str = Field(
        default="postgresql+asyncpg://neondb_owner:npg_9Yn2OWpAegBw@ep-fragrant-sky-aogk3l4j.c-2.ap-southeast-1.aws.neon.tech/neondb?ssl=require",
        description="Database connection URL"
    )

    # ── Security ──
    encryption_key: str = Field(default="Hd5ngo0dIhZip2Br04AVOqkMoQw7k1jjDlchAhwbaOQ=", description="Fernet key for API key encryption")
    jwt_secret_key: str = Field(default="Hd5ngo0dIhZip2Br04AVOqkMoQw7k1jjDlchAhwbaOQ=", description="JWT signing secret")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiry_minutes: int = Field(default=1440, description="JWT token expiry in minutes")

    # ── Telegram ──
    telegram_bot_token: str = Field(default="8973560314:AAEpQWBP-gc2mex03qg8d_JQYL9RAZ5D6pU", description="Telegram Bot API token")
    telegram_chat_id: str = Field(default="8044668960", description="Default Telegram chat ID for alerts")

    # ── Application ──
    app_env: AppEnvironment = Field(default=AppEnvironment.DEVELOPMENT)
    log_level: str = Field(default="INFO", description="Logging level")

    # ── Email (SMTP for OTP) ──
    email_host: str = Field(default="smtp.gmail.com", description="SMTP host")
    email_port: int = Field(default=465, description="SMTP port")
    email_user: str = Field(default="", description="SMTP username/email")
    email_password: str = Field(default="", description="SMTP password or app password")

    # ── SMS (Fast2SMS India for OTP) ──
    fast2sms_api_key: str = Field(default="", description="Fast2SMS API key for India SMS OTP")

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @property
    def base_url(self) -> str:
        """Get the Delta Exchange API base URL for the configured region."""
        urls = {
            ExchangeRegion.GLOBAL: "https://api.delta.exchange",
            ExchangeRegion.INDIA: "https://api.india.delta.exchange",
        }
        return urls[self.delta_exchange_region]

    @property
    def is_production(self) -> bool:
        return self.app_env == AppEnvironment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env == AppEnvironment.DEVELOPMENT


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.
    Call this function to access configuration anywhere in the app.
    """
    return Settings()


# ── Constants (Non-configurable) ──

# Delta Exchange API endpoints
ENDPOINTS = {
    "candles": "/v2/history/candles",
    "products": "/v2/products",
    "product_by_symbol": "/v2/products/{symbol}",
    "place_order": "/v2/orders",
    "cancel_order": "/v2/orders",
    "active_orders": "/v2/orders",
    "bracket_order": "/v2/orders/bracket",
    "positions_margined": "/v2/positions/margined",
    "position": "/v2/positions",
    "order_leverage": "/v2/products/{product_id}/orders/leverage",
    "wallet_balances": "/v2/wallet/balances",
    "order_history": "/v2/orders/history",
    "fills": "/v2/fills",
    "ticker": "/v2/tickers/{symbol}",
    "l2_orderbook": "/v2/l2orderbook/{symbol}",
}

# Candle resolution mapping (user-friendly -> API param)
TIMEFRAME_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "2h": "2h",
    "4h": "4h",
    "6h": "6h",
    "1d": "1d",
    "7d": "7d",
    "30d": "30d",
    "1w": "1w",
    "2w": "2w",
}

# Maximum candles per API request (Delta Exchange limit)
MAX_CANDLES_PER_REQUEST = 2000
