from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult

router = APIRouter()


@router.get("/intelligence/runs/{run_id}")
async def get_run_status(
    run_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    run = (
        await db.execute(
            select(IntelligenceRun).where(
                IntelligenceRun.id == run_id,
                IntelligenceRun.org_id == org_id,
            )
        )
    ).scalar_one_or_none()

    if not run:
        return {"error": "run_not_found"}

    partial = (
        await db.execute(
            select(IntelligenceResult).where(
                IntelligenceResult.run_id == run_id,
                IntelligenceResult.org_id == org_id,
                IntelligenceResult.type == "ocr_text_partial",
            )
        )
    ).scalar_one_or_none()

    return {
        "id": str(run.id),
        "org_id": str(run.org_id),
        "asset_id": str(run.asset_id),
        "processor_name": run.processor_name,
        "processor_version": run.processor_version,
        "status": run.status,
        "error_message": run.error_message,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "estimated_cost_cents": getattr(run, "estimated_cost_cents", 0),
        "input_fingerprint_signature": getattr(run, "input_fingerprint_signature", None),
        "retry_count": getattr(run, "retry_count", 0),
        "last_retry_at": getattr(run, "last_retry_at", None),
        "cancel": {
            "cancel_requested": getattr(run, "cancel_requested", False),
            "canceled_at": getattr(run, "canceled_at", None),
        },
        "progress": {
            "current": getattr(run, "progress_current", 0),
            "total": getattr(run, "progress_total", None),
            "message": getattr(run, "progress_message", None),
        },
        "partial_result": (partial.data if partial else None),
    }
