"""
Slancio Crypto Algo Treding Engine — Background Scheduler
===========================================================
Automatically triggers the bot logic precisely every hour.
"""

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from sqlalchemy import select

from database.connection import AsyncSessionLocal
from core.security import security
from database.models import User, ApiKey
from core.engine import TradingEngine

scheduler = AsyncIOScheduler()

async def run_bot_job():
    logger.info("⏰ Hourly Scheduler Triggered: Running Slancio Engine Cycle...")
    
    # 1. Check if ANY user has the bot toggled ON via the Dashboard
    async with AsyncSessionLocal() as session:
        # Get active users who have bot_enabled=True and join with their API Keys
        from sqlalchemy.orm import selectinload
        stmt = select(User).where(User.bot_enabled == True).options(selectinload(User.api_keys))
        result = await session.execute(stmt)
        active_users = result.scalars().all()
        
        if not active_users:
            logger.info("⏸️ Engine is paused in the dashboard for all users. Skipping this hour.")
            return

        # For multi-tenant, we would loop over all active_users. 
        # For now, we just take the first one (admin).
        user = active_users[0]
        if not user.api_keys:
            logger.error(f"❌ User {user.email} has bot enabled but no API keys saved! Skipping.")
            return
            
        db_keys = user.api_keys[0]
        try:
            api_key = security.decrypt(db_keys.encrypted_api_key)
            api_secret = security.decrypt(db_keys.encrypted_api_secret)
        except Exception as e:
            logger.error(f"❌ Failed to decrypt API keys for {user.email}. Are they corrupted? {e}")
            return

    # 2. Run the heavy trading logic in a background thread 
    # (so we don't block the FastAPI web server from responding to clicks)
    engine = TradingEngine(api_key=api_key, api_secret=api_secret)
    
    try:
        await asyncio.to_thread(engine.run_candle_cycle)
    except Exception as e:
        logger.error(f"❌ Critical Error during bot cycle: {e}")


def start_scheduler():
    """Initializes and starts the background cron job"""
    if not scheduler.running:
        # We trigger at minute=0 and second=5 (e.g. 13:00:05).
        # We add 5 seconds to guarantee Delta Exchange has published the new closed candle.
        scheduler.add_job(run_bot_job, 'cron', minute=0, second=5, id='hourly_bot_cycle')
        
        # For testing right now, let's also run it once immediately if desired, 
        # but in production we only want the cron job.
        
        scheduler.start()
        logger.success("⏱️ Background APScheduler started! Slancio Engine is now fully autonomous.")
