"""
Slancio Crypto Algo Treding Engine — Users API
=================================
Manage API keys, Bot Toggle, and Settings.
"""

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.dependencies import get_current_user, get_db_session
from database.models import User, ApiKey
from core.security import security

router = APIRouter(prefix="/api/users", tags=["users"])


class ApiKeyCreate(BaseModel):
    api_key: str
    api_secret: str
    exchange: str = "delta_india"


class BotToggle(BaseModel):
    enabled: bool


@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "bot_enabled": current_user.bot_enabled
    }


@router.post("/keys")
async def save_api_keys(
    data: ApiKeyCreate, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Encrypt and save API keys"""
    
    # Check if key already exists, update it if so
    stmt = select(ApiKey).where(ApiKey.user_id == current_user.id)
    result = await db.execute(stmt)
    existing_key = result.scalar_one_or_none()
    
    enc_key = security.encrypt(data.api_key)
    enc_secret = security.encrypt(data.api_secret)
    
    if existing_key:
        existing_key.encrypted_api_key = enc_key
        existing_key.encrypted_api_secret = enc_secret
        existing_key.exchange = data.exchange
    else:
        new_key = ApiKey(
            user_id=current_user.id,
            encrypted_api_key=enc_key,
            encrypted_api_secret=enc_secret,
            exchange=data.exchange
        )
        db.add(new_key)
        
    await db.commit()
    return {"status": "success", "message": "API keys encrypted and saved securely."}


@router.post("/bot/toggle")
async def toggle_bot(
    data: BotToggle, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Start or Pause the trading bot for the user"""
    # Check if they have API keys before enabling
    if data.enabled:
        stmt = select(ApiKey).where(ApiKey.user_id == current_user.id)
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Cannot enable bot without saving API keys first.")
            
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
