from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.services.intelligence_service import enqueue_processor_run
from app.models.intelligence_run import IntelligenceRun

router = APIRouter()


@router.post("/assets/{asset_id}/intelligence/image-metadata", status_code=202)
async def analyze_image_metadata(
    asset_id: UUID,
    background_tasks: BackgroundTasks,
    force: bool = Query(False, description="If true, always create a new run."),
    retry: bool = Query(False, description="If true, create a new run only if the latest failed."),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    run = await enqueue_processor_run(
        db,
        org_id=org_id,
        asset_id=asset_id,
        processor_name="image-metadata",
        background_tasks=background_tasks,
        force=force,
        retry=retry,
    )

    return {
        "run_id": run.id,
        "status": run.status,
        "processor": run.processor_name,
        "version": run.processor_version,
    }


@router.post("/assets/{asset_id}/intelligence/fingerprint", status_code=202)
async def analyze_fingerprint(
    asset_id: UUID,
    background_tasks: BackgroundTasks,
    force: bool = Query(False, description="If true, always create a new run."),
    retry: bool = Query(False, description="If true, create a new run only if the latest failed."),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    run = await enqueue_processor_run(
        db,
        org_id=org_id,
        asset_id=asset_id,
        processor_name="asset-fingerprint",
        background_tasks=background_tasks,
        force=force,
        retry=retry,
    )

    return {
        "run_id": run.id,
        "status": run.status,
        "processor": run.processor_name,
        "version": run.processor_version,
    }


@router.get("/assets/{asset_id}/intelligence/runs")
async def get_asset_intelligence_runs(
    asset_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    result = await db.execute(
        select(IntelligenceRun)
        .where(
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.org_id == org_id,
        )
        .order_by(IntelligenceRun.created_at.desc())
    )
    runs = result.scalars().all()

    return [
        {
            "id": run.id,
            "asset_id": run.asset_id,
            "processor_name": run.processor_name,
            "processor_version": run.processor_version,
            "status": run.status,
            "error_message": run.error_message,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
            "estimated_cost_cents": getattr(run, "estimated_cost_cents", 0),
            "input_fingerprint_signature": getattr(run, "input_fingerprint_signature", None),
        }
        for run in runs
    ]


@router.get("/assets/{asset_id}/intelligence/runs/latest")
async def get_latest_run_for_processor(
    asset_id: UUID,
    processor: str,
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    result = await db.execute(
        select(IntelligenceRun)
        .where(
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.processor_name == processor,
        )
        .order_by(IntelligenceRun.created_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if not run:
        return None

    return {
        "id": run.id,
        "status": run.status,
        "processor": run.processor_name,
        "version": run.processor_version,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "error_message": run.error_message,
        "estimated_cost_cents": getattr(run, "estimated_cost_cents", 0),
        "input_fingerprint_signature": getattr(run, "input_fingerprint_signature", None),
    }

@router.post("/assets/{asset_id}/intelligence/ocr", status_code=202)
async def analyze_ocr(
    asset_id: UUID,
    background_tasks: BackgroundTasks,
    lang: str = Query("eng", description="Tesseract language code, e.g. eng"),
    force: bool = Query(False),
    retry: bool = Query(False),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    # NOTE: we are not passing lang into the background handler yet because our registry handler
    # signature is (db, run_id). Keeping this lean for now.
    # If you want per-request lang support, see the optional section below.

    run = await enqueue_processor_run(
        db,
        org_id=org_id,
        asset_id=asset_id,
        processor_name="ocr-text",
        background_tasks=background_tasks,
        force=force,
        retry=retry,
    )

    return {
        "run_id": run.id,
        "status": run.status,
        "processor": run.processor_name,
        "version": run.processor_version,
        "note": f"OCR language parameter '{lang}' currently defaults to 'eng' in processor. "
                f"Add per-run config in Phase 6.3.1 if needed.",
    }