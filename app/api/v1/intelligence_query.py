from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.services.intelligence_query_service import (
    get_intelligence_for_asset,
    get_latest_intelligence_by_type,
)

router = APIRouter()


@router.get("/assets/{asset_id}/intelligence")
async def list_asset_intelligence(
    asset_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    intel = await get_intelligence_for_asset(
        db=db,
        asset_id=asset_id,
        org_id=org_id,
    )
    return {
        "asset_id": asset_id,
        "intelligence": intel,
    }


@router.get("/assets/{asset_id}/intelligence/{intel_type}/latest")
async def get_latest_intelligence(
    asset_id: UUID,
    intel_type: str,
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    result = await get_latest_intelligence_by_type(
        db=db,
        asset_id=asset_id,
        org_id=org_id,
        intel_type=intel_type,
    )
    if not result:
        raise HTTPException(status_code=404, detail="No intelligence found")

    return result
