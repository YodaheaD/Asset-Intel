from fastapi import Depends, HTTPException
from app.security.context import RequestContext
from typing import List

def require_role(*allowed_roles: List[str]):
    """
    Factory dependency to enforce roles.
    Usage in route: Depends(require_role("admin", "member"))
    """
    def guard(ctx: RequestContext = Depends()):
        if ctx.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return ctx
    return guard
