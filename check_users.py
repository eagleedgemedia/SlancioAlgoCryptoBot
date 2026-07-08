import asyncio
from database.connection import AsyncSessionLocal
from database.models import User
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()
        for u in users:
            print(f"User: {u.username}, {u.email}, {u.mobile_number}")
        if not users:
            print("DB is completely empty!")

if __name__ == "__main__":
    asyncio.run(check())
