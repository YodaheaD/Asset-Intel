from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.services.deadletter_service import (
    list_deadletters_for_org,
    requeue_deadletter_run,
    requeue_latest_deadletter_for_asset,
)

router = APIRouter()


def _require_admin(x_admin_key: str | None) -> None:
    if not settings.ADMIN_API_ENABLED:
        raise HTTPException(status_code=404, detail="Admin API not enabled")
    if not settings.ADMIN_KEY:
        raise HTTPException(status_code=500, detail="ADMIN_KEY not configured")
    if not x_admin_key or x_admin_key != settings.ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/admin/deadletter/intelligence_runs")
async def admin_list_deadletters(
    limit: int = Query(50, ge=1, le=200),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    _require_admin(x_admin_key)
    return await list_deadletters_for_org(db, org_id=org_id, limit=limit)


@router.post("/admin/deadletter/intelligence_runs/{run_id}/requeue")
async def admin_requeue_deadletter(
    run_id: UUID,
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    _require_admin(x_admin_key)
    return await requeue_deadletter_run(db, org_id=org_id, run_id=run_id)


@router.post("/admin/deadletter/assets/{asset_id}/requeue_latest")
async def admin_requeue_latest_deadletter_for_asset(
    asset_id: UUID,
    processor_name: str = Query("ocr-text", description="Processor to requeue (default ocr-text)"),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    _require_admin(x_admin_key)
    return await requeue_latest_deadletter_for_asset(
        db,
        org_id=org_id,
        asset_id=asset_id,
        processor_name=processor_name,
    )
