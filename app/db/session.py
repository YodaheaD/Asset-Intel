from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


engine = create_async_engine(settings.DATABASE_URL, future=True, echo=False)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Keep compatibility with your existing imports:
# async with async_session() as db:
async_session = AsyncSessionLocal


async def get_async_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
