from uuid import UUID

from fastapi import APIRouter, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.models.asset_search_index import AssetSearchIndex
from app.models.intelligence_run import IntelligenceRun
from app.services.indexing_workflow_service import ensure_asset_indexing

router = APIRouter()


@router.get("/assets/{asset_id}/index/status")
async def index_status(
    asset_id: UUID,
    auto_retry_ocr: bool = Query(False, description="If true, may auto-retry failed OCR when missing."),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
    background_tasks: BackgroundTasks = None,
):
    idx = (
        await db.execute(
            select(AssetSearchIndex).where(
                AssetSearchIndex.org_id == org_id,
                AssetSearchIndex.asset_id == asset_id,
            )
        )
    ).scalar_one_or_none()

    fingerprint_indexed = False
    ocr_indexed = False
    if idx:
        fingerprint_indexed = bool(idx.sha256 or idx.etag)
        ocr_indexed = idx.ocr_tsv is not None

    # Optional auto-retry path (only if OCR missing)
    if auto_retry_ocr and not ocr_indexed:
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
            # Return 202 if we started work
            return JSONResponse(
                status_code=202,
                content={
                    "asset_id": str(asset_id),
                    "status": "indexing",
                    **status,
                },
            )

        # If indexed became true, re-fetch
        idx = (
            await db.execute(
                select(AssetSearchIndex).where(
                    AssetSearchIndex.org_id == org_id,
                    AssetSearchIndex.asset_id == asset_id,
                )
            )
        ).scalar_one_or_none()
        fingerprint_indexed = bool(idx and (idx.sha256 or idx.etag))
        ocr_indexed = bool(idx and (idx.ocr_tsv is not None))

    # Latest runs for UI debugging/status
    runs = (
        await db.execute(
            select(IntelligenceRun)
            .where(
                IntelligenceRun.org_id == org_id,
                IntelligenceRun.asset_id == asset_id,
                IntelligenceRun.processor_name.in_(["asset-fingerprint", "ocr-text"]),
            )
            .order_by(IntelligenceRun.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    latest_by_proc = {}
    for r in runs:
        if r.processor_name not in latest_by_proc:
            latest_by_proc[r.processor_name] = {
                "id": str(r.id),
                "processor_name": r.processor_name,
                "processor_version": r.processor_version,
                "status": r.status,
                "created_at": r.created_at,
                "completed_at": r.completed_at,
                "error_message": r.error_message,
                "estimated_cost_cents": getattr(r, "estimated_cost_cents", 0),
                "input_fingerprint_signature": getattr(r, "input_fingerprint_signature", None),
                "retry_count": getattr(r, "retry_count", 0),
                "last_retry_at": getattr(r, "last_retry_at", None),
            }

    return {
        "asset_id": str(asset_id),
        "index_row_exists": idx is not None,
        "fingerprint_indexed": fingerprint_indexed,
        "ocr_indexed": ocr_indexed,
        "ready_for_related": fingerprint_indexed,
        "ready_for_search": ocr_indexed,
        "latest_runs": latest_by_proc,
    }
