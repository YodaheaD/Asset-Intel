from pydantic import BaseModel
from typing import Literal, Optional
from uuid import UUID

class RequestContext(BaseModel):
    """
    Trusted request context.
    This is the only object your routes should ever trust for user + tenant info.
    """
    tenant_id: UUID
    user_id: Optional[UUID] = None  # Optional for API keys only
    role: Literal["owner", "admin", "member", "service"]
    auth_type: Literal["api_key", "jwt"]
