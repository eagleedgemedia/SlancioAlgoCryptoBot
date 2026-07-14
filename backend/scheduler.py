"""
Slancio Crypto Algo Treding Engine — Background Scheduler
===========================================================
- Runs trading bot logic every hour at :00:05
- Pings /api/health every 10 minutes to keep Render free-tier alive
- Sends Telegram heartbeat alert every 6 hours to confirm bot is alive
"""

import asyncio
import httpx
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.connection import AsyncSessionLocal
from core.security import security
from database.models import User, ApiKey, TradeLog
from core.engine import TradingEngine
from core.exchange.position_manager import ActivePosition
from core.config import get_settings

settings = get_settings()
scheduler = AsyncIOScheduler()

# ─── Self-Ping to Keep Render Free Tier Alive ───
async def keep_alive_ping():
    """
    Pings the app's own /api/health endpoint every 5 minutes.
    Render free tier spins down after 15 minutes of inactivity. Internal pings don't work,
    so we MUST hit the external URL to route through Render's load balancer.
    """
    import os
    # Prefer the specific URL, fallback to env var
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://slancioalgotradebot.onrender.com")

    try:
        # Don't verify SSL in case of temporary cert issues, use external URL
        async with httpx.AsyncClient(timeout=10, verify=False) as client:
            resp = await client.get(f"{render_url}/api/health")
            logger.info(f"🏓 Keep-alive ping → {resp.status_code} | Server is awake at {render_url}")
    except Exception as e:
        logger.warning(f"⚠️ Keep-alive ping failed: {e}")


# ─── Telegram Heartbeat Alert ───
async def send_heartbeat():
    """Send a Telegram message every 6 hours confirming the bot is alive."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    try:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        msg = (
            f"💚 *Slancio Algo Engine — Heartbeat*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 Time: `{now}`\n"
            f"🟢 Status: *ONLINE & RUNNING*\n"
            f"🤖 Scheduler: Active\n"
            f"🗄️ Database: Connected\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"_Auto-heartbeat every 6 hours_"
        )
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json={
                "chat_id": settings.telegram_chat_id,
                "text": msg,
                "parse_mode": "Markdown"
            })
        logger.info("💚 Telegram heartbeat sent.")
    except Exception as e:
        logger.warning(f"Heartbeat send failed: {e}")


# ─── Main Bot Trading Cycle ───
async def run_bot_job():
    logger.info("⏰ Hourly Scheduler Triggered: Running Slancio Engine Cycle...")

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(
            (User.bot_enabled == True) &
            (User.is_active == True)
        ).options(
            selectinload(User.api_keys),
            selectinload(User.settings)
        )
        result = await session.execute(stmt)
        active_users = result.scalars().all()

        if not active_users:
            logger.info("⏸️ No active users with bot enabled. Skipping cycle.")
            return

        for user in active_users:
            # No API keys? We will just fall back to DRY RUN alerts!
            try:
                # Find selected key
                db_key = next((k for k in user.api_keys if getattr(k, "is_selected", False)), None)
                if not db_key and len(user.api_keys) > 0:
                    # If none selected, default to first (legacy fallback)
                    db_key = user.api_keys[0]

                if db_key:
                    api_key = security.decrypt(db_key.encrypted_api_key)
                    api_secret = security.decrypt(db_key.encrypted_api_secret)
                else:
                    api_key = None
                    api_secret = None
                    logger.info(f"User {user.username} has no active API keys. Running in DRY RUN mode for alerts only.")

                user_telegram_chat_id = user.settings.telegram_chat_id if user.settings else None
                
                # Get open trade log
                stmt_open = select(TradeLog).where(
                    TradeLog.user_id == user.id,
                    TradeLog.status == "open"
                )
                result_open = await session.execute(stmt_open)
                open_trade = result_open.scalar_one_or_none()

                # Use user's personal settings
                engine = TradingEngine(
                    api_key=api_key,
                    api_secret=api_secret,
                    user_id=user.id,
                    stop_loss_points=user.stop_loss_points,
                    ema_distance_points=getattr(user, "ema_distance_points", 200),
                    telegram_chat_id=user_telegram_chat_id
                )
                
                # Hydrate position manager
                if open_trade:
                    engine.position_manager.active_position = ActivePosition(
                        symbol=open_trade.symbol,
                        side=open_trade.side,
                        size=open_trade.quantity,
                        entry_price=open_trade.entry_price,
                        stop_loss=open_trade.stop_loss,
                        take_profit_target=open_trade.take_profit_target,
                        mode="live_open" if api_key else "virtual_open"
                    )

                logger.info(f"🚀 Running engine for user: {user.username}")
                events = await asyncio.to_thread(engine.run_candle_cycle)
                
                # Process events to update DB
                if events:
                    for ev in events:
                        if ev["type"] == "open":
                            t = ev["order_data"]
                            sig = ev["signal"]
                            new_log = TradeLog(
                                user_id=user.id,
                                symbol=t["symbol"],
                                side=t["side"],
                                status="open",
                                entry_price=sig.entry_price,
                                stop_loss=sig.stop_loss,
                                take_profit_target=sig.take_profit_target,
                                quantity=t["size"],
                                leverage=user.max_leverage,
                                entry_order_id=t.get("id")
                            )
                            session.add(new_log)
                            await session.commit()
                            
                        elif ev["type"] == "close":
                            if open_trade:
                                open_trade.status = "closed"
                                open_trade.exit_price = ev["exit_price"]
                                open_trade.pnl_usdt = ev["pnl"]
                                open_trade.closed_at = datetime.now(timezone.utc)
                                await session.commit()
                                # After a close event, if there are more events they would be a new open, open_trade needs to be re-queried or set to None
                                open_trade = None

            except Exception as e:
                logger.error(f"❌ Engine error for {user.username}: {e}")


# ─── Scheduler Startup ───
def start_scheduler():
    """Initialize APScheduler with all jobs."""
    if scheduler.running:
        return

    # 1. Main trading cycle — every 1 minute
    scheduler.add_job(
        run_bot_job, 'cron',
        minute='*', second=5,
        id='minute_bot_cycle',
        name='Minute Trading Cycle',
        misfire_grace_time=30
    )

    # 2. Keep-alive self-ping — every 5 minutes
    scheduler.add_job(
        keep_alive_ping, 'interval',
        minutes=5,
        id='keep_alive',
        name='Render Keep-Alive Ping',
    )

    # 3. Telegram heartbeat — every 6 hours
    scheduler.add_job(
        send_heartbeat, 'interval',
        hours=6,
        id='heartbeat',
        name='Telegram Heartbeat',
    )

    scheduler.start()
    logger.success("⏱️ APScheduler started with 3 jobs: Trading | Keep-Alive | Heartbeat")
