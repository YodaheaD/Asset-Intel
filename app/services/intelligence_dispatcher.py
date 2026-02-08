from __future__ import annotations

from uuid import UUID
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_run import IntelligenceRun

from app.services.intelligence_processors import PROCESSORS


async def dispatch_run(db: AsyncSession, run_id: UUID) -> None:
    """
    Load the run record and dispatch to the correct processor.
    """
    run = (
        await db.execute(select(IntelligenceRun).where(IntelligenceRun.id == run_id))
    ).scalar_one_or_none()

    if not run:
        return

    if run.status in ("completed", "failed", "canceled"):
        return

    try:
        spec = PROCESSORS.get(run.processor_name)
        if not spec:
            await db.execute(
                update(IntelligenceRun)
                .where(IntelligenceRun.id == run_id)
                .values(
                    status="failed",
                    error_message=f"Unknown processor_name: {run.processor_name}",
                    completed_at=datetime.utcnow(),
                )
            )
            await db.commit()
            return

        await spec.handler(db, run_id)

    except Exception as e:
        # As a last-resort catch: mark failed (processors usually do this already,
        # but this guarantees DB reflects failure if something leaks).
        await db.execute(
            update(IntelligenceRun)
            .where(IntelligenceRun.id == run_id)
            .values(
                status="failed",
                error_message=str(e),
                completed_at=datetime.utcnow(),
            )
        )
        await db.commit()
        raise
