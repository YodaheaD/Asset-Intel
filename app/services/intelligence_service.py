from __future__ import annotations

from uuid import UUID
from datetime import datetime

from fastapi import BackgroundTasks
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_run import IntelligenceRun
from app.services.intelligence_processors import PROCESSORS

from app.services.quota_service import enforce_quota
from app.core.pricing import estimate_cost
from app.services.usage_service import record_usage
from app.services.fingerprint_signature_service import get_latest_fingerprint_signature


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

    # Phase 4: enforce quotas BEFORE creating any new runs
    await enforce_quota(db, org_id=org_id)

    # Phase 6.2: compute "current" fingerprint signature for smart reprocessing
    # - only for non-fingerprint processors
    current_sig = None
    if spec.name != "asset-fingerprint":
        current_sig = await get_latest_fingerprint_signature(
            db,
            org_id=org_id,
            asset_id=asset_id,
        )

    # Find latest run for (org, asset, processor, version)
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

    # Smart reuse logic:
    # - If idempotency says "reuse", require signature match when we have a signature
    if latest and not _should_create_new_run(latest.status, force=force, retry=retry):
        # If we don't know the fingerprint signature yet, fall back to old idempotency behavior
        if current_sig is None:
            return latest

        # Only reuse completed/pending/running run if it was created for the same input signature
        if latest.input_fingerprint_signature == current_sig:
            return latest

        # Otherwise: fingerprint changed => fall through to create a new run

    # Create new run
    run = IntelligenceRun(
        org_id=org_id,
        asset_id=asset_id,
        processor_name=spec.name,
        processor_version=spec.version,
        status="pending",
        error_message=None,
        created_at=datetime.utcnow(),
        input_fingerprint_signature=current_sig if spec.name != "asset-fingerprint" else None,
        estimated_cost_cents=0,  # will be set after success
    )

    db.add(run)
    await db.commit()
    await db.refresh(run)

    # Kick off background execution with a fresh session
    background_tasks.add_task(run_processor_in_background, run.id, spec.name)

    return run


async def run_processor_in_background(run_id: UUID, processor_name: str) -> None:
    """
    BackgroundTasks runs after response. We create a new AsyncSession to avoid
    reusing a request-scoped session.
    """
    from app.db.session import AsyncSessionLocal  # async_sessionmaker

    if processor_name not in PROCESSORS:
        # cannot process; nothing to do
        return

    spec = PROCESSORS[processor_name]
    cost = estimate_cost(processor_name)

    async with AsyncSessionLocal() as db:
        try:
            # Run the processor
            await spec.handler(db, run_id)

            # Fetch run to get org_id (and ensure it exists)
            run_res = await db.execute(
                select(IntelligenceRun).where(IntelligenceRun.id == run_id)
            )
            run = run_res.scalar_one_or_none()
            if not run:
                return

            # Record usage + persist cost on the run only after success
            await record_usage(db, org_id=run.org_id, cost_cents=cost)

            await db.execute(
                update(IntelligenceRun)
                .where(IntelligenceRun.id == run_id)
                .values(estimated_cost_cents=cost)
            )
            await db.commit()

        except Exception as e:
            # Mark run failed; Stripe/web/etc retries are separate concerns
            await db.execute(
                update(IntelligenceRun)
                .where(IntelligenceRun.id == run_id)
                .values(status="failed", error_message=str(e))
            )
            await db.commit()
