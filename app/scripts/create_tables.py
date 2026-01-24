# app/scripts/create_tables.py
import asyncio
from app.db.base import Base
from app.db.session import engine

# Import models here so metadata knows about them
from app.models.organization import Organization
from app.models.api_key import ApiKey
from app.models.asset import Asset

async def create_all_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

asyncio.run(create_all_tables())
