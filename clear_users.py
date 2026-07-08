import asyncio
from database.connection import AsyncSessionLocal, Base, engine
from database.models import User, OTPRecord, ApiKey, TradeLog
from sqlalchemy import delete

async def clear_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Successfully dropped and recreated all tables!")

if __name__ == "__main__":
    asyncio.run(clear_db())
