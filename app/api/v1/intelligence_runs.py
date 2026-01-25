from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.models.intelligence_run import IntelligenceRun

router = APIRouter()


@router.get("/intelligence/runs/{run_id}")
async def get_run_status(
    run_id: UUID,
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(IntelligenceRun).where(IntelligenceRun.id == run_id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "id": run.id,
        "status": run.status,
        "processor": run.processor_name,
        "version": run.processor_version,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "error": run.error_message,
    }
