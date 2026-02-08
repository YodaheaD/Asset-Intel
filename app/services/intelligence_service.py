from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session
from app.models.intelligence_run import IntelligenceRun
from app.services.intelligence_dispatcher import dispatch_run
from app.services.job_queue import enqueue_process_run


PROCESSOR_VERSIONS = {
    "asset-fingerprint": "1.0.0",
    "ocr-text": "1.0.0",
}


async def _dispatch_run_in_new_session(run_id: UUID) -> None:
    """
    Dev fallback: dispatch a run using a fresh DB session so we don't reuse
    request-scoped sessions that may be closed when BackgroundTasks executes.
    """
    async with async_session() as db:
        await dispatch_run(db, run_id)


async def enqueue_processor_run(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    processor_name: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    retry: bool = False,
) -> IntelligenceRun:
    """
    Create a new run record and enqueue processing.
    """
    processor_version = PROCESSOR_VERSIONS.get(processor_name, "1.0.0")

    # If retry=True, only proceed when latest run for processor failed
    if retry:
        latest = (
            await db.execute(
                select(IntelligenceRun)
                .where(
                    IntelligenceRun.org_id == org_id,
                    IntelligenceRun.asset_id == asset_id,
                    IntelligenceRun.processor_name == processor_name,
                )
                .order_by(IntelligenceRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if latest and latest.status != "failed":
            return latest

    run = IntelligenceRun(
        id=uuid.uuid4(),
        org_id=org_id,
        asset_id=asset_id,
        processor_name=processor_name,
        processor_version=processor_version,
        status="pending",
        error_message=None,
        created_at=datetime.utcnow(),
        completed_at=None,
        estimated_cost_cents=0,
    )

    db.add(run)
    await db.commit()
    await db.refresh(run)

    if settings.USE_ARQ_WORKER:
        await enqueue_process_run(run.id)
    else:
        background_tasks.add_task(_dispatch_run_in_new_session, run.id)

    return run
