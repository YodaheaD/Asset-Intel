from fastapi import APIRouter, Depends, status, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.intelligence import process_asset

from app.schemas.asset import AssetCreate, AssetRead
from app.services.asset_service import AssetService
from app.db.session import get_db
from sqlalchemy import select
from app.models.asset import Asset

router = APIRouter(prefix="/assets", tags=["assets"])


@router.post(
    "",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_asset(
    asset_in: AssetCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    asset = await AssetService.create_asset(db, asset_in)

    background_tasks.add_task(
        process_asset,
        asset.id,  # ← ONLY pass the ID
    )


    return asset


@router.get(
    "/{asset_id}",
    response_model=AssetRead,
)
async def get_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id)
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    return asset