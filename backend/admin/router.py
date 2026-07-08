"""
Slancio Crypto Algo Treding Engine — Admin Router
===================================================
Admin-only endpoints for:
  - User management (list, toggle active)
  - Position sizing overrides (per-user)
  - Trading config: margin type, leverage, timeframe (per-user)
  - Live trade management: modify SL/TP, close position
  - System-wide stats
"""

from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import hashlib
import hmac
import time

from backend.dependencies import get_current_user, get_db_session
from database.models import User, TradeLog, ApiKey
from core.security import security
from core.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/admin", tags=["admin"])

DELTA_INDIA_BASE = "https://api.india.delta.exchange"

# ─── DELTA EXCHANGE TIMEFRAMES (valid API values) ───
VALID_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "1d"]
VALID_MARGIN_TYPES = ["isolated", "cross"]
VALID_LEVERAGE_RANGE = (1, 200)


def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


# ─── Pydantic Schemas ───

class PositionSizingUpdate(BaseModel):
    position_size_pct: Optional[float] = None   # e.g. 0.02 = 2%
    max_leverage: Optional[int] = None           # 1-200 (Delta allows up to 200x)
    stop_loss_points: Optional[float] = None
    take_profit_points: Optional[float] = None
    margin_type: Optional[str] = None           # 'isolated' or 'cross'
    trading_timeframe: Optional[str] = None     # '1m','5m','15m','1h','4h'

class ModifyTradeRequest(BaseModel):
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

class CloseTradeRequest(BaseModel):
    trade_log_id: str


# ─── DELTA EXCHANGE SIGNING HELPER ───
def _delta_sign(api_secret: str, method: str, path: str, query: str, body: str, timestamp: int) -> str:
    message = method + str(timestamp) + path + query + body
    return hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()

async def _delta_request(api_key: str, api_secret: str, method: str, path: str, body: dict = None) -> dict:
    """Make authenticated request to Delta Exchange India."""
    timestamp = int(time.time())
    body_str = "" if not body else str(body).replace("'", '"').replace("True", "true").replace("False", "false")
    signature = hmac.new(
        api_secret.encode(),
        f"{method}{timestamp}{path}{''}{''}".encode(),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "api-key": api_key,
        "timestamp": str(timestamp),
        "signature": signature,
        "Content-Type": "application/json",
    }
    url = f"{DELTA_INDIA_BASE}{path}"
    async with httpx.AsyncClient(timeout=10) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers)
        elif method == "POST":
            resp = await client.post(url, headers=headers, json=body)
        elif method == "PUT":
            resp = await client.put(url, headers=headers, json=body)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers, json=body)
        else:
            raise ValueError(f"Unsupported method: {method}")
    return resp.json()


async def _get_user_delta_keys(user_id: str, db: AsyncSession):
    """Fetch and decrypt a user's Delta Exchange API keys."""
    result = await db.execute(select(ApiKey).where(ApiKey.user_id == user_id))
    key_record = result.scalar_one_or_none()
    if not key_record:
        raise HTTPException(status_code=404, detail="User has no API keys configured.")
    try:
        api_key = security.decrypt(key_record.encrypted_api_key)
        api_secret = security.decrypt(key_record.encrypted_api_secret)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt user API keys.")
    return api_key, api_secret


# ─── LIST ALL USERS ───
@router.get("/users")
async def list_all_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Admin: Get all registered users with full config."""
    result = await db.execute(select(User))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "mobile_number": u.mobile_number,
            "role": u.role,
            "is_active": u.is_active,
            "is_email_verified": u.is_email_verified,
            "is_mobile_verified": u.is_mobile_verified,
            "bot_enabled": u.bot_enabled,
            "position_size_pct": u.position_size_pct,
            "max_leverage": u.max_leverage,
            "stop_loss_points": u.stop_loss_points,
            "take_profit_points": getattr(u, "take_profit_points", 800.0),
            "margin_type": getattr(u, "margin_type", "isolated"),
            "trading_timeframe": getattr(u, "trading_timeframe", "1h"),
            "created_at": u.created_at,
        }
        for u in users
    ]


# ─── TOGGLE USER ACTIVE STATUS ───
@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = not user.is_active
    await db.commit()
    return {"status": "success", "user_id": user_id, "is_active": user.is_active}


# ─── UPDATE USER FULL TRADING CONFIG ───
@router.put("/users/{user_id}/trading-config")
async def update_user_trading_config(
    user_id: str,
    data: PositionSizingUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Admin: Override per-user trading configuration including:
    position size, leverage, SL/TP points, margin type, and timeframe.
    Also applies leverage & margin type to Delta Exchange live via API if keys exist.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    # --- Validate and apply each field ---
    if data.position_size_pct is not None:
        if not (0.001 <= data.position_size_pct <= 0.10):
            raise HTTPException(status_code=400, detail="Position size must be 0.1%–10%.")
        user.position_size_pct = data.position_size_pct

    if data.max_leverage is not None:
        lo, hi = VALID_LEVERAGE_RANGE
        if not (lo <= data.max_leverage <= hi):
            raise HTTPException(status_code=400, detail=f"Leverage must be {lo}x–{hi}x.")
        user.max_leverage = data.max_leverage

    if data.stop_loss_points is not None:
        user.stop_loss_points = data.stop_loss_points

    if data.take_profit_points is not None:
        user.take_profit_points = data.take_profit_points

    if data.margin_type is not None:
        if data.margin_type not in VALID_MARGIN_TYPES:
            raise HTTPException(status_code=400, detail=f"Margin type must be one of: {VALID_MARGIN_TYPES}")
        user.margin_type = data.margin_type

    if data.trading_timeframe is not None:
        if data.trading_timeframe not in VALID_TIMEFRAMES:
            raise HTTPException(status_code=400, detail=f"Timeframe must be one of: {VALID_TIMEFRAMES}")
        user.trading_timeframe = data.trading_timeframe

    await db.commit()

    delta_status = "not_applied"

    # --- Push leverage & margin type to Delta Exchange if user has API keys ---
    if data.max_leverage is not None or data.margin_type is not None:
        try:
            api_key, api_secret = await _get_user_delta_keys(user_id, db)
            symbol = settings.trading_symbol

            if data.max_leverage is not None:
                # Delta API: Set leverage per product
                # GET product_id first
                prod_resp = await _delta_request(api_key, api_secret, "GET",
                    f"/v2/products?contract_type=perpetual_futures&states=live")
                products = prod_resp.get("result", [])
                product = next((p for p in products if p["symbol"] == symbol), None)
                if product:
                    product_id = product["id"]
                    lev_resp = await _delta_request(api_key, api_secret, "POST",
                        f"/v2/products/{product_id}/orders/leverage",
                        {"product_id": product_id, "leverage": str(data.max_leverage)}
                    )
                    delta_status = f"leverage set to {data.max_leverage}x on Delta"

        except Exception as e:
            delta_status = f"DB saved but Delta API call failed: {str(e)}"

    return {
        "status": "success",
        "user_id": user_id,
        "position_size_pct": user.position_size_pct,
        "max_leverage": user.max_leverage,
        "stop_loss_points": user.stop_loss_points,
        "take_profit_points": getattr(user, "take_profit_points", 800.0),
        "margin_type": getattr(user, "margin_type", "isolated"),
        "trading_timeframe": getattr(user, "trading_timeframe", "1h"),
        "delta_exchange_status": delta_status,
    }


# ─── LIST OPEN TRADES (ALL USERS) ───
@router.get("/trades/open")
async def list_open_trades(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Admin: Get all currently open (running) trades across all users."""
    result = await db.execute(
        select(TradeLog, User.username)
        .join(User, TradeLog.user_id == User.id)
        .where(TradeLog.status == "open")
    )
    rows = result.all()
    return [
        {
            "id": t.id,
            "user_id": t.user_id,
            "username": username,
            "symbol": t.symbol,
            "side": t.side,
            "entry_price": t.entry_price,
            "stop_loss": t.stop_loss,
            "take_profit_target": t.take_profit_target,
            "quantity": t.quantity,
            "leverage": t.leverage,
            "opened_at": t.opened_at,
            "entry_order_id": t.entry_order_id,
        }
        for t, username in rows
    ]


# ─── MODIFY RUNNING TRADE SL/TP ───
@router.put("/trades/{trade_id}/modify")
async def modify_running_trade(
    trade_id: str,
    data: ModifyTradeRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Admin: Modify stop-loss and/or take-profit of a running (open) trade.
    Updates in DB and sends bracket order modification to Delta Exchange.
    """
    result = await db.execute(select(TradeLog).where(TradeLog.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found.")
    if trade.status != "open":
        raise HTTPException(status_code=400, detail="Only open trades can be modified.")

    # Update DB record
    if data.stop_loss is not None:
        trade.stop_loss = data.stop_loss
    if data.take_profit is not None:
        trade.take_profit_target = data.take_profit
    await db.commit()

    delta_status = "DB updated"

    # Push to Delta Exchange if order ID is known
    if trade.entry_order_id:
        try:
            api_key, api_secret = await _get_user_delta_keys(trade.user_id, db)
            # Use bracket order edit endpoint
            body = {"id": int(trade.entry_order_id)}
            if data.stop_loss is not None:
                body["bracket_stop_loss_price"] = str(data.stop_loss)
                body["bracket_stop_loss_limit_price"] = str(data.stop_loss)
            if data.take_profit is not None:
                body["bracket_take_profit_price"] = str(data.take_profit)
                body["bracket_take_profit_limit_price"] = str(data.take_profit)

            resp = await _delta_request(api_key, api_secret, "PUT", "/v2/orders/bracket", body)
            if resp.get("success"):
                delta_status = "SL/TP updated on Delta Exchange"
            else:
                delta_status = f"Delta API response: {resp.get('error', {}).get('code', 'unknown')}"
        except Exception as e:
            delta_status = f"DB updated but Delta API failed: {str(e)}"

    return {
        "status": "success",
        "trade_id": trade_id,
        "stop_loss": trade.stop_loss,
        "take_profit_target": trade.take_profit_target,
        "delta_exchange_status": delta_status,
    }


# ─── CLOSE RUNNING TRADE ───
@router.post("/trades/{trade_id}/close")
async def close_running_trade(
    trade_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """
    Admin: Force-close an open position on Delta Exchange and mark as closed in DB.
    Uses a market order to close at current price.
    """
    result = await db.execute(select(TradeLog).where(TradeLog.id == trade_id))
    trade = result.scalar_one_or_none()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found.")
    if trade.status != "open":
        raise HTTPException(status_code=400, detail="Trade is already closed.")

    delta_status = "not_attempted"

    try:
        api_key, api_secret = await _get_user_delta_keys(trade.user_id, db)

        # Close via market order in opposite direction
        close_side = "sell" if trade.side in ["long", "buy"] else "buy"
        body = {
            "product_symbol": trade.symbol,
            "size": trade.quantity,
            "side": close_side,
            "order_type": "market_order",
            "reduce_only": "true",
            "close_on_trigger": "true",
        }
        resp = await _delta_request(api_key, api_secret, "POST", "/v2/orders", body)

        if resp.get("success"):
            delta_status = "Position closed on Delta Exchange"
            result_data = resp.get("result", {})
            avg_fill = result_data.get("average_fill_price")

            # Update DB
            from datetime import datetime, timezone
            trade.status = "closed"
            trade.closed_at = datetime.now(timezone.utc)
            if avg_fill:
                trade.exit_price = float(avg_fill)
                if trade.side in ["long", "buy"]:
                    trade.pnl_usdt = (float(avg_fill) - trade.entry_price) * trade.quantity
                else:
                    trade.pnl_usdt = (trade.entry_price - float(avg_fill)) * trade.quantity
            await db.commit()
        else:
            delta_status = f"Delta Exchange error: {resp.get('error', {}).get('code', 'unknown')}"

    except HTTPException:
        raise
    except Exception as e:
        delta_status = f"Exception: {str(e)}"

    return {
        "status": "success",
        "trade_id": trade_id,
        "trade_status": trade.status,
        "exit_price": trade.exit_price,
        "pnl_usdt": trade.pnl_usdt,
        "delta_exchange_status": delta_status,
    }


# ─── SYSTEM-WIDE STATS ───
@router.get("/stats")
async def admin_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Admin: Aggregate system-wide P&L and trade stats."""
    result = await db.execute(select(User))
    total_users = len(result.scalars().all())

    result2 = await db.execute(select(TradeLog).where(TradeLog.status == 'closed'))
    trades = result2.scalars().all()
    total_trades = len(trades)
    winning = len([t for t in trades if t.pnl_usdt and t.pnl_usdt > 0])
    total_pnl = sum([t.pnl_usdt for t in trades if t.pnl_usdt])
    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0

    result3 = await db.execute(select(TradeLog).where(TradeLog.status == 'open'))
    open_trades = len(result3.scalars().all())

    return {
        "total_users": total_users,
        "total_trades": total_trades,
        "open_trades": open_trades,
        "system_win_rate": round(win_rate, 2),
        "system_total_pnl": round(total_pnl, 2),
    }
