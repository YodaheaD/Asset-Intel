from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.models.org_usage import OrgUsage

router = APIRouter()


@router.get("/billing/usage")
async def get_current_usage(
    db: AsyncSession = Depends(get_async_db),
    org_id = Depends(get_current_org_id),
):
    result = await db.execute(
        select(OrgUsage)
        .where(OrgUsage.org_id == org_id)
        .order_by(OrgUsage.period.desc())
        .limit(1)
    )
    usage = result.scalar_one_or_none()

    return usage or {
        "intelligence_runs": 0,
        "estimated_cost_cents": 0,
        "period": None,
    }
