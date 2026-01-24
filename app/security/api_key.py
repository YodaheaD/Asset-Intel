import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models.api_key import ApiKey

def hash_key(raw_key: str) -> str:
    """Hashes API key for storage / comparison."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def validate_api_key(db: AsyncSession, api_key: str) -> ApiKey:
    """
    Validate API key and return the ApiKey record.
    Raises HTTPException if invalid.
    """
    key_hash = hash_key(api_key)

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active.is_(True),
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return record
