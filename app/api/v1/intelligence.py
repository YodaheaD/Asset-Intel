from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from typing import List

from app.db.session import get_async_db 
from app.services.intelligence_service import enqueue_image_metadata
from app.api.deps import get_current_org_id
from app.models.intelligence_run import IntelligenceRun

router = APIRouter()


@router.post("/assets/{asset_id}/intelligence/image-metadata", status_code=202)
async def analyze_image_metadata(
    asset_id: UUID,
    background_tasks: BackgroundTasks,
    db = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    run = await enqueue_image_metadata(
        db=db,
        asset_id=asset_id,
        org_id=org_id,
        background_tasks=background_tasks,
    )

    return {
        "run_id": run.id,
        "status": run.status,
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
        }
        for run in runs
    ]