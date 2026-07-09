"""
Slancio Crypto Algo Treding Engine — Users API
=================================
Manage API keys, Bot Toggle, and Settings.
"""

from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.dependencies import get_current_user, get_db_session
from database.models import User, ApiKey
from core.security import security

router = APIRouter(prefix="/api/users", tags=["users"])


class ApiKeyCreate(BaseModel):
    api_name: str = "Primary API"
    api_key: str
    api_secret: str
    exchange: str = "delta_india"


class BotToggle(BaseModel):
    enabled: bool


class PositionSizingUpdate(BaseModel):
    position_size_pct: Optional[float] = None   # 0.001 - 0.10
    max_leverage: Optional[int] = None           # 1 - 20
    stop_loss_points: Optional[float] = None     # e.g. 400.0


@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "mobile_number": current_user.mobile_number,
        "role": current_user.role,
        "bot_enabled": current_user.bot_enabled,
        "is_email_verified": current_user.is_email_verified,
        "is_mobile_verified": current_user.is_mobile_verified,
        "position_size_pct": current_user.position_size_pct,
        "max_leverage": current_user.max_leverage,
        "stop_loss_points": current_user.stop_loss_points,
    }


@router.put("/position-sizing")
async def update_my_position_sizing(
    data: PositionSizingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """User updates their own position sizing preferences."""
    if data.position_size_pct is not None:
        if not (0.001 <= data.position_size_pct <= 0.10):
            raise HTTPException(status_code=400, detail="Position size must be between 0.1% and 10%.")
        current_user.position_size_pct = data.position_size_pct
    if data.max_leverage is not None:
        if not (1 <= data.max_leverage <= 20):
            raise HTTPException(status_code=400, detail="Leverage must be between 1x and 20x.")
        current_user.max_leverage = data.max_leverage
    if data.stop_loss_points is not None:
        current_user.stop_loss_points = data.stop_loss_points
    await db.commit()
    return {"status": "success", "message": "Position sizing updated.", "position_size_pct": current_user.position_size_pct, "max_leverage": current_user.max_leverage}


@router.get("/keys")
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List all API keys for the user (names only)"""
    stmt = select(ApiKey).where(ApiKey.user_id == current_user.id)
    result = await db.execute(stmt)
    keys = result.scalars().all()
    return [
        {
            "id": k.id,
            "api_name": getattr(k, "api_name", "Primary API"),
            "exchange": k.exchange,
            "is_selected": getattr(k, "is_selected", False),
            "created_at": k.created_at
        } for k in keys
    ]


@router.post("/keys")
async def save_api_keys(
    data: ApiKeyCreate, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Encrypt and add a new API key profile"""
    enc_key = security.encrypt(data.api_key)
    enc_secret = security.encrypt(data.api_secret)
    
    # Check if this is their first key
    stmt = select(ApiKey).where(ApiKey.user_id == current_user.id)
    result = await db.execute(stmt)
    first_key = result.scalars().first() is None
    
    new_key = ApiKey(
        user_id=current_user.id,
        api_name=data.api_name,
        encrypted_api_key=enc_key,
        encrypted_api_secret=enc_secret,
        exchange=data.exchange,
        is_selected=first_key  # Auto-select if it's the first one
    )
    db.add(new_key)
    await db.commit()
    return {"status": "success", "message": f"API key '{data.api_name}' saved securely."}


@router.post("/keys/{key_id}/select")
async def select_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Set the specified API key as the active key for trading"""
    stmt = select(ApiKey).where(ApiKey.user_id == current_user.id)
    result = await db.execute(stmt)
    keys = result.scalars().all()
    
    found = False
    for k in keys:
        if k.id == key_id:
            # If already selected, toggle it OFF (fallback to Dry Run)
            k.is_selected = not k.is_selected
            found = True
        else:
            k.is_selected = False
            
    if not found:
        raise HTTPException(status_code=404, detail="API key not found.")
        
    await db.commit()
    return {"status": "success", "message": "API key toggled."}


@router.delete("/keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete an API key profile"""
    stmt = select(ApiKey).where(ApiKey.user_id == current_user.id, ApiKey.id == key_id)
    result = await db.execute(stmt)
    key = result.scalar_one_or_none()
    
    if not key:
        raise HTTPException(status_code=404, detail="API key not found.")
        
    await db.delete(key)
    await db.commit()
    
    # If the deleted key was selected, auto-select another one if available
    if getattr(key, "is_selected", False):
        stmt2 = select(ApiKey).where(ApiKey.user_id == current_user.id)
        res = await db.execute(stmt2)
        next_key = res.scalars().first()
        if next_key:
            next_key.is_selected = True
            await db.commit()
            
    return {"status": "success", "message": "API key deleted."}


@router.get("/keys/{key_id}/balance")
async def get_key_balance(
    key_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Fetch live margin balance for a specific API key"""
    from backend.admin.router import _delta_request
    from loguru import logger
    
    stmt = select(ApiKey).where(ApiKey.user_id == current_user.id, ApiKey.id == key_id)
    result = await db.execute(stmt)
    key = result.scalar_one_or_none()
    
    if not key:
        raise HTTPException(status_code=404, detail="API key not found.")
        
    try:
        api_key = security.decrypt(key.encrypted_api_key)
        api_secret = security.decrypt(key.encrypted_api_secret)
        
        resp = await _delta_request(api_key, api_secret, "GET", "/v2/wallet/balances")
        if resp.get("success"):
            balances = resp.get("result", [])
            inr_margin = 0.0
            usdt_margin = 0.0
            for b in balances:
                if b.get("asset_symbol") in ["USD", "USDT"]:
                    usdt_margin = float(b.get("available_balance", b.get("balance", 0)))
                    inr_margin = float(b.get("available_balance_inr", b.get("balance_inr", 0)))
                elif b.get("asset_symbol") == "INR" and inr_margin == 0.0:
                    inr_margin = float(b.get("available_balance", b.get("balance", 0)))
                    
            return {"status": "success", "margin_inr": inr_margin, "margin_usdt": usdt_margin}
                
        logger.error(f"Delta API error for key {key_id}: {resp}")
        return {"status": "error", "margin_inr": 0.0, "margin_usdt": 0.0, "message": resp.get("error", "Unknown Delta API error")}
    except Exception as e:
        logger.warning(f"Could not fetch margin for key {key_id}: {e}")
        return {"status": "error", "margin_inr": 0.0, "margin_usdt": 0.0}



@router.post("/bot/toggle")
async def toggle_bot(
    data: BotToggle, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Start or Pause the trading bot for the user"""
    # Allow enabling for Paper Trading / Alert generation even if no keys
    # Keys will be checked during the engine cycle.
    current_user.bot_enabled = data.enabled
    await db.commit()
    
    return {"status": "success", "bot_enabled": current_user.bot_enabled}


from database.models import TradeLog
from sqlalchemy import func

@router.get("/trades")
async def get_trade_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Fetch user's trade history"""
    stmt = select(TradeLog).where(TradeLog.user_id == current_user.id).order_by(TradeLog.opened_at.desc()).limit(50)
    result = await db.execute(stmt)
    trades = result.scalars().all()
    
    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "status": t.status,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "pnl_usdt": t.pnl_usdt,
            "pnl_percent": t.pnl_percent,
            "opened_at": t.opened_at,
            "closed_at": t.closed_at
        } for t in trades
    ]


@router.get("/stats")
async def get_trade_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Fetch user's P&L and win rate"""
    stmt = select(TradeLog).where(TradeLog.user_id == current_user.id, TradeLog.status == 'closed')
    result = await db.execute(stmt)
    trades = result.scalars().all()
    
    total_trades = len(trades)
    winning_trades = len([t for t in trades if t.pnl_usdt and t.pnl_usdt > 0])
    total_pnl = sum([t.pnl_usdt for t in trades if t.pnl_usdt])
    
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "total_trades": total_trades,
        "win_rate": round(win_rate, 2),
        "total_pnl": round(total_pnl, 2)
    }
