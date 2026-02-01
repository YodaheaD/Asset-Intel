from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.services.intelligence_summary_service import build_asset_intelligence_summary

router = APIRouter()


@router.get("/assets/{asset_id}/intelligence/summary")
async def get_asset_intelligence_summary(
    asset_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    return await build_asset_intelligence_summary(
        db,
        org_id=org_id,
        asset_id=asset_id,
    )
