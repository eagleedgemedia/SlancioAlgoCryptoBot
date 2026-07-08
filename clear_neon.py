import asyncio
from database.connection import engine
from database.models import Base

async def clear_db():
    async with engine.begin() as conn:
        print("Dropping all tables in Neon Database...")
        await conn.run_sync(Base.metadata.drop_all)
        print("Recreating all tables with new schema...")
        await conn.run_sync(Base.metadata.create_all)
    print("Success! Database wiped and recreated perfectly.")

if __name__ == "__main__":
    asyncio.run(clear_db())
