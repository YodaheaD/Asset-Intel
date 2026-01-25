from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult


async def get_intelligence_for_asset(
    db: AsyncSession,
    asset_id: UUID,
    org_id: UUID,
) -> list[dict[str, Any]]:
    """
    Returns all completed intelligence runs + results for an asset.
    Efficient async implementation (no db.query, no N+1).
    """
    runs_result = await db.execute(
        select(IntelligenceRun)
        .where(
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.status == "completed",
        )
        .order_by(IntelligenceRun.created_at.desc())
    )
    runs = runs_result.scalars().all()

    if not runs:
        return []

    run_ids = [r.id for r in runs]

    results_result = await db.execute(
        select(IntelligenceResult)
        .where(IntelligenceResult.run_id.in_(run_ids))
    )
    results = results_result.scalars().all()

    results_by_run: dict[UUID, list[IntelligenceResult]] = defaultdict(list)
    for r in results:
        results_by_run[r.run_id].append(r)

    response: list[dict[str, Any]] = []
    for run in runs:
        response.append(
            {
                "run_id": run.id,
                "processor": run.processor_name,
                "version": run.processor_version,
                "completed_at": run.completed_at,
                "results": [
                    {
                        "type": r.type,
                        "data": r.data,
                        "confidence": r.confidence,
                    }
                    for r in results_by_run.get(run.id, [])
                ],
            }
        )

    return response


async def get_latest_intelligence_by_type(
    db: AsyncSession,
    asset_id: UUID,
    org_id: UUID,
    intel_type: str,
) -> dict[str, Any] | None:
    """
    Returns the most recent result of a given intelligence type for an asset.
    """
    stmt = (
        select(IntelligenceResult, IntelligenceRun)
        .join(IntelligenceRun, IntelligenceRun.id == IntelligenceResult.run_id)
        .where(
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.status == "completed",
            IntelligenceResult.type == intel_type,
        )
        .order_by(IntelligenceRun.completed_at.desc())
        .limit(1)
    )

    row = (await db.execute(stmt)).first()
    if not row:
        return None

    result, run = row  # (IntelligenceResult, IntelligenceRun)

    return {
        "type": result.type,
        "data": result.data,
        "confidence": result.confidence,
        "run_id": result.run_id,
        "completed_at": run.completed_at,
        "processor": run.processor_name,
        "version": run.processor_version,
    }
