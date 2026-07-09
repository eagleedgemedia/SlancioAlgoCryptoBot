
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = 'postgresql+asyncpg://neondb_owner:npg_9Yn2OWpAegBw@ep-fragrant-sky-aogk3l4j.c-2.ap-southeast-1.aws.neon.tech/neondb?ssl=require'

async def check_db():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        result = await conn.execute(text('SELECT id, api_name FROM api_keys'))
        rows = result.fetchall()
        print('API Keys in DB:', rows)
        
        # Check column type
        result = await conn.execute(text('SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ''api_keys'' AND column_name = ''id'''))
        cols = result.fetchall()
        print('ID Column Type:', cols)

asyncio.run(check_db())

