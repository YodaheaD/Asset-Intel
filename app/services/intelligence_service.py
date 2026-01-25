from __future__ import annotations

from uuid import UUID
from datetime import datetime

from fastapi import BackgroundTasks
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_run import IntelligenceRun
from app.services.intelligence_processors import PROCESSORS
from app.services.quota_service import enforce_quota
from app.services.usage_service import record_usage
from app.core.pricing import estimate_cost


def _should_create_new_run(
    latest_status: str,
    *,
    force: bool,
    retry: bool,
) -> bool:
    """
    Default behavior: idempotent
      - pending/running -> reuse existing
      - completed -> reuse existing
      - failed -> reuse existing unless retry or force
    """
    if force:
        return True

    if latest_status in ("pending", "running", "completed"):
        return False

    if latest_status == "failed":
        return retry  # only create a new one if retry=True

    # unknown status: safest is to avoid duplicating
    return False


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
    if processor_name not in PROCESSORS:
        raise ValueError(f"Unknown processor: {processor_name}")

    spec = PROCESSORS[processor_name]

    # Find latest run for this (org, asset, processor, version)
    latest_res = await db.execute(
        select(IntelligenceRun)
        .where(
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.processor_name == spec.name,
            IntelligenceRun.processor_version == spec.version,
        )
        .order_by(IntelligenceRun.created_at.desc())
        .limit(1)
    )
    latest = latest_res.scalar_one_or_none()

    if latest and not _should_create_new_run(latest.status, force=force, retry=retry):
        return latest

    # Enforce quota before creating a new run
    await enforce_quota(db, org_id=org_id)

    # Create a new run
    run = IntelligenceRun(
        org_id=org_id,
        asset_id=asset_id,
        processor_name=spec.name,
        processor_version=spec.version,
        status="pending",
        error_message=None,
        created_at=datetime.utcnow(),
    )

    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Kick off background execution with a *fresh* db session (safer)
    background_tasks.add_task(run_processor_in_background, run.id, spec.name)

    return run


async def run_processor_in_background(run_id: UUID, processor_name: str) -> None:
    """
    BackgroundTasks runs after response. We create a new AsyncSession
    to avoid reusing request-scoped session.
    """
    from app.db.session import AsyncSessionLocal  # async_sessionmaker

    spec = PROCESSORS[processor_name]

    async with AsyncSessionLocal() as db:
        # Get the run object to access org_id
        run_result = await db.execute(
            select(IntelligenceRun).where(IntelligenceRun.id == run_id)
        )
        run = run_result.scalar_one()
        
        try:
            await spec.handler(db, run_id)
            
            # Record usage and cost after successful execution
            cost = estimate_cost(processor_name)
            
            await record_usage(
                db,
                org_id=run.org_id,
                cost_cents=cost,
            )
            
            await db.execute(
                update(IntelligenceRun)
                .where(IntelligenceRun.id == run_id)
                .values(estimated_cost_cents=cost)
            )
            await db.commit()
            
        except Exception as e:
            await db.rollback()  # <-- important
            
            # Mark run failed
            await db.execute(
                update(IntelligenceRun)
                .where(IntelligenceRun.id == run_id)
                .values(status="failed", error_message=str(e))
            )
            await db.commit()
