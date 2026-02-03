from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.services.cancel_run_service import (
    request_cancel_run,
    request_cancel_latest_run_for_asset,
)

router = APIRouter()


@router.post("/intelligence/runs/{run_id}/cancel")
async def cancel_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    return await request_cancel_run(db, org_id=org_id, run_id=run_id)


@router.post("/assets/{asset_id}/intelligence/{processor_name}/cancel")
async def cancel_latest_run_for_asset(
    asset_id: UUID,
    processor_name: str,
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    """
    Cancel the latest active run for an asset+processor.
    Examples:
      - POST /assets/{asset_id}/intelligence/ocr-text/cancel
      - POST /assets/{asset_id}/intelligence/asset-fingerprint/cancel

    Aliases accepted (normalized):
      - ocr, ocr_text -> ocr-text
      - fingerprint -> asset-fingerprint
    """
    return await request_cancel_latest_run_for_asset(
        db,
        org_id=org_id,
        asset_id=asset_id,
        processor_name=processor_name,
    )
