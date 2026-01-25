from fastapi import APIRouter, Depends, status, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.intelligence import process_asset

from app.schemas.asset import AssetCreate, AssetRead
from app.services.asset_service import AssetService
from app.db.session import get_async_db 
from sqlalchemy import select
from app.models.asset import Asset
from app.core.auth import get_current_org
from app.security.authorization import require_role
from app.security.dependencies import get_request_context
from app.security.context import RequestContext
router = APIRouter(prefix="/assets", tags=["assets"])


# @router.post("", response_model=AssetRead)
# async def create_asset(
#     asset_in: AssetCreate,
#     background_tasks: BackgroundTasks,
#     org_id = Depends(get_current_org),
#     db: AsyncSession = Depends(get_async_db ),
# ):
#     asset = await AssetService.create_asset(
#         db,
#         asset_in,
#         org_id=org_id,
#     )

#     background_tasks.add_task(process_asset, asset.id, db)
#     return asset

@router.post("", response_model=AssetRead)
async def create_asset(
    asset_in: AssetCreate,
    db: AsyncSession = Depends(get_async_db ),
    ctx: RequestContext = Depends(get_request_context),  # <- injected
):
    # tenant_id, role, auth_type come from ctx
    tenant_id = ctx.tenant_id

    asset = await AssetService.create_asset(
        db,
        asset_in,
        org_id=tenant_id,
    )
    return asset
@router.get(
    "/{asset_id}",
    response_model=AssetRead,
)
async def get_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_async_db ),
    ctx: RequestContext = Depends(get_request_context),  # <- injected
):
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id)
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    return asset