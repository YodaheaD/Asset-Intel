from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.models.organization import Organization
from app.services.stripe_service import create_customer, create_subscription

router = APIRouter()


@router.post("/billing/upgrade")
async def upgrade_plan(
    plan: str,
    db: AsyncSession = Depends(get_async_db),
    org_id = Depends(get_current_org_id),
):
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one()

    if org.plan == plan:
        return {"status": "already_on_plan", "plan": plan}

    if not org.stripe_customer_id:
        customer_id = create_customer(org.name)
        org.stripe_customer_id = customer_id

    create_subscription(org.stripe_customer_id, plan)

    org.plan = plan
    await db.commit()

    return {"status": "upgraded", "plan": plan}
