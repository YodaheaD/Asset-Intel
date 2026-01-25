from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org_usage import OrgUsage


def _current_period() -> str:
    now = datetime.utcnow()
    return f"{now.year}-{now.month:02d}"


async def record_usage(
    db: AsyncSession,
    *,
    org_id,
    cost_cents: int,
):
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
        usage = OrgUsage(
            org_id=org_id,
            period=period,
            intelligence_runs=0,
            estimated_cost_cents=0,
        )
        db.add(usage)

    usage.intelligence_runs += 1
    usage.estimated_cost_cents += cost_cents

    await db.commit()
