from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.security.context import RequestContext
from app.security.api_key import validate_api_key

async def get_request_context(
    x_api_key: str = Header(..., description="API Key for authentication"),
    db: AsyncSession = Depends(get_db),
) -> RequestContext:
    """
    FastAPI dependency that validates API key and returns a typed RequestContext.
    All routes must depend on this.
    """
    api_key_record = await validate_api_key(db, x_api_key)

    ctx = RequestContext(
        tenant_id=api_key_record.org_id,
        user_id=None,  # Could be filled for JWT later
        role=api_key_record.role,
        auth_type="api_key",
    )
    return ctx
