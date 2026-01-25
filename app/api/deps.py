from fastapi import Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_async_db 
from app.models.api_key import ApiKey
import hashlib


# -----------------------------
# Helper: Hash API Key
# -----------------------------
def hash_key(raw_key: str) -> str:
    """
    Returns a SHA256 hash of the API key.
    """
    return hashlib.sha256(raw_key.encode()).hexdigest()


# -----------------------------
# Dependency: Get Current Org ID (Async)
# -----------------------------
async def get_current_org_id(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_async_db ),
) -> str:
    """
    Async FastAPI dependency to get the organization ID for the request.
    Raises 401 if the API key is invalid or inactive.
    """

    key_hash = hash_key(x_api_key)

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active.is_(True)
        )
    )
    api_key = result.scalars().first()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key.org_id
