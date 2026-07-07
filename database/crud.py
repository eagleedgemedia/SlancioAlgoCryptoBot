"""
Slancio Crypto Algo Treding Engine — Basic CRUD Operations
==============================================
Provides common database operations for the bot.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
from database.models import User, TradeLog
from core.strategy.signals import TradeSignal


async def create_user(session: AsyncSession, username: str, email: str, password_hash: str) -> User:
    """Create a new system user."""
    user = User(username=username, email=email, password_hash=password_hash)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info(f"Created new user: {username}")
    return user


async def log_trade_entry(
    session: AsyncSession,
    user_id: str,
    symbol: str,
    signal: TradeSignal,
    size: int,
    leverage: int,
    order_id: str,
) -> TradeLog:
    """Record a new trade entry in the database."""
    trade = TradeLog(
        user_id=user_id,
        symbol=symbol,
        side=signal.signal_type.value,
        status="open",
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profit_target=signal.take_profit_target,
        quantity=size,
        leverage=leverage,
        entry_order_id=order_id,
        strategy_metadata=signal.to_dict()
    )
    
    session.add(trade)
    await session.commit()
    await session.refresh(trade)
    logger.info(f"💾 Logged new trade entry into DB (ID: {trade.id})")
    return trade


async def log_trade_exit(
    session: AsyncSession,
    trade_id: str,
    exit_price: float,
    exit_order_id: str,
    status: str = "closed"
) -> TradeLog:
    """Update an existing trade record when closed."""
    stmt = select(TradeLog).where(TradeLog.id == trade_id)
    result = await session.execute(stmt)
    trade = result.scalar_one_or_none()
    
    if not trade:
        logger.error(f"Cannot log exit: Trade {trade_id} not found in DB.")
        return None
        
    trade.exit_price = exit_price
    trade.exit_order_id = exit_order_id
    trade.status = status
    
    # Calculate simple PnL per contract
    if trade.side == "short":
        trade.pnl_usdt = trade.entry_price - exit_price
    else:
        trade.pnl_usdt = exit_price - trade.entry_price
        
    import datetime
    trade.closed_at = datetime.datetime.now(datetime.timezone.utc)
    
    await session.commit()
    await session.refresh(trade)
    logger.info(f"💾 Updated trade {trade.id} with exit data (PnL: {trade.pnl_usdt:.2f})")
    return trade
