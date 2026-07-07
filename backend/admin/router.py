"""
Slancio Crypto Algo Treding Engine — Admin Router
===================================================
Admin-only endpoints for user management, position sizing overrides,
and system control.
"""

from pydantic import BaseModel
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.dependencies import get_current_user, get_db_session
from database.models import User, TradeLog

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user


class PositionSizingUpdate(BaseModel):
    position_size_pct: Optional[float] = None   # e.g. 0.02 = 2%
    max_leverage: Optional[int] = None
    stop_loss_points: Optional[float] = None


# ─── LIST ALL USERS ───
@router.get("/users")
async def list_all_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Admin: Get all registered users."""
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
    """Admin: Enable or disable a user account."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    user.is_active = not user.is_active
    await db.commit()
    return {"status": "success", "user_id": user_id, "is_active": user.is_active}


# ─── UPDATE USER POSITION SIZING ───
@router.put("/users/{user_id}/position-sizing")
async def update_user_position_sizing(
    user_id: str,
    data: PositionSizingUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session)
):
    """Admin: Override position sizing settings for a specific user."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if data.position_size_pct is not None:
        if not (0.001 <= data.position_size_pct <= 0.10):
            raise HTTPException(status_code=400, detail="Position size must be between 0.1% and 10%.")
        user.position_size_pct = data.position_size_pct
    if data.max_leverage is not None:
        if not (1 <= data.max_leverage <= 20):
            raise HTTPException(status_code=400, detail="Leverage must be between 1x and 20x.")
        user.max_leverage = data.max_leverage
    if data.stop_loss_points is not None:
        user.stop_loss_points = data.stop_loss_points

    await db.commit()
    return {
        "status": "success",
        "user_id": user_id,
        "position_size_pct": user.position_size_pct,
        "max_leverage": user.max_leverage,
        "stop_loss_points": user.stop_loss_points,
    }


# ─── ADMIN TRADE STATS (ALL USERS) ───
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

    return {
        "total_users": total_users,
        "total_trades": total_trades,
        "system_win_rate": round(win_rate, 2),
        "system_total_pnl": round(total_pnl, 2),
    }
