"""
Slancio Crypto Algo Treding Engine — Database Connection
============================================
Async SQLAlchemy session management.
"""

from typing import AsyncGenerator
from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from core.config import get_settings

settings = get_settings()

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI endpoints and Engine to get a database session.
    Automatically closes the session when done.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
            
async def init_db_schema():
    """
    Initialize the database schema (creates all tables).
    Works for both SQLite (dev) and PostgreSQL (production Neon).
    Also handles missing columns via safe ALTER TABLE migrations.
    """
    from database.models import Base
    
    logger.info(f"Connecting to DB: {settings.database_url[:40]}...")
    try:
        async with engine.begin() as conn:
            # Create all tables that don't exist yet
            await conn.run_sync(Base.metadata.create_all)
            
            # --- Safe column migrations for Postgres (ALTER TABLE IF NOT EXISTS) ---
            # These run only when the column doesn't exist yet, so safe to run every startup.
            if "postgresql" in settings.database_url:
                migrations = [
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_number VARCHAR",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN DEFAULT FALSE",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_mobile_verified BOOLEAN DEFAULT TRUE",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS position_size_pct FLOAT DEFAULT 0.02",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS max_leverage INTEGER DEFAULT 10",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS stop_loss_points FLOAT DEFAULT 400.0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS take_profit_points FLOAT DEFAULT 800.0",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS margin_type VARCHAR DEFAULT 'isolated'",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS trading_timeframe VARCHAR DEFAULT '1h'",
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ema_distance_points INTEGER DEFAULT 200",
                ]
                for stmt in migrations:
                    try:
                        await conn.execute(text(stmt))
                        logger.debug(f"Migration OK: {stmt[:60]}")
                    except Exception as me:
                        logger.warning(f"Migration skipped (already applied): {me}")
                        
        logger.success("✅ Database schema initialized successfully.")
        
        # --- Seed Default Admin User ---
        from database.models import User
        from backend.auth.security import get_password_hash
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.username == "Admin"))
            admin_user = result.scalar_one_or_none()
            if not admin_user:
                logger.info("🌱 Seeding default Admin user...")
                new_admin = User(
                    username="Admin",
                    email="admin@slancio.io",
                    mobile_number="0000000000",
                    password_hash=get_password_hash("RagiKaushal@2616"),
                    role="admin",
                    is_active=True,
                    is_email_verified=True,
                    is_mobile_verified=True,
                    bot_enabled=False
                )
                session.add(new_admin)
                await session.commit()
                logger.success("✅ Default Admin user created: Admin / RagiKaushal@2616")
            else:
                # Force update password to ensure it matches the requested default
                admin_user.password_hash = get_password_hash("RagiKaushal@2616")
                admin_user.role = "admin"
                await session.commit()
                logger.info("✅ Default Admin user password updated to RagiKaushal@2616")
                    
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
