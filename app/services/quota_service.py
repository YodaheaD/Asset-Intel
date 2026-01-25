from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.org_usage import OrgUsage
from app.core.quotas import DEFAULT_QUOTAS
from app.services.usage_service import _current_period


async def enforce_quota(db: AsyncSession, *, org_id):
    period = _current_period()

    result = await db.execute(
        select(OrgUsage)
        .where(
            OrgUsage.org_id == org_id,
            OrgUsage.period == period,
        )
    )
    usage = result.scalar_one_or_none()

    if not usage:
        return  # no usage yet → allowed

    if usage.intelligence_runs >= DEFAULT_QUOTAS["max_runs_per_month"]:
        raise HTTPException(
            status_code=429,
            detail="Monthly intelligence run quota exceeded",
        )

    if usage.estimated_cost_cents >= DEFAULT_QUOTAS["max_cost_cents_per_month"]:
        raise HTTPException(
            status_code=402,
            detail="Monthly cost quota exceeded",
        )
