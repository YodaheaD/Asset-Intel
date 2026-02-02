from uuid import UUID

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.services.related_assets_service import find_related_assets
from app.services.indexing_workflow_service import ensure_asset_indexing

router = APIRouter()


@router.get("/assets/{asset_id}/related")
async def related_assets(
    asset_id: UUID,
    limit_per_bucket: int = Query(20, ge=1, le=100),
    ensure_index: bool = Query(True, description="If true, auto-start fingerprint/OCR indexing when missing."),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
    background_tasks: BackgroundTasks = None,
):
    if ensure_index:
        bg = background_tasks or BackgroundTasks()
        status = await ensure_asset_indexing(
            db,
            org_id=org_id,
            asset_id=asset_id,
            background_tasks=bg,
            ensure_fingerprint=True,
            ensure_ocr=True,
        )
        if not status["indexed"]:
            return JSONResponse(
                status_code=202,
                content={
                    "asset_id": str(asset_id),
                    "status": "indexing",
                    **status,
                },
            )

    return await find_related_assets(
        db,
        org_id=org_id,
        asset_id=asset_id,
        limit_per_bucket=limit_per_bucket,
    )
