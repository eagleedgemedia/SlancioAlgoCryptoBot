"""
Slancio Crypto Algo Treding Engine — Database Connection
============================================
Async SQLAlchemy session management.
"""

from typing import AsyncGenerator
from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from core.config import get_settings

settings = get_settings()

# Create async engine
# If using SQLite, ensure the path is absolute or correct relative to the execution context
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    # SQLite-specific args to avoid threading issues
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
    Safe to call on every startup — SQLAlchemy skips existing tables.
    """
    from database.models import Base
    
    logger.info(f"Connecting to DB: {settings.database_url[:40]}...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.success("✅ Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
