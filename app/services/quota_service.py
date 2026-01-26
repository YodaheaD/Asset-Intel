# app/services/quota_service.py

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.quotas import PLAN_QUOTAS, DEFAULT_PLAN
from app.models.org_usage import OrgUsage
from app.models.organization import Organization
from app.services.usage_service import _current_period


async def enforce_quota(db: AsyncSession, *, org_id):
    """
    Enforce monthly per-org quotas based on the organization's current plan.

    - Looks up Organization.plan
    - Uses PLAN_QUOTAS[plan], falling back to DEFAULT_PLAN if plan missing/unknown
    - Checks current-period OrgUsage totals
    """
    period = _current_period()

    # 1) Fetch org plan
    org_res = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = org_res.scalar_one_or_none()
    if not org:
        # If org doesn't exist, treat as unauthorized
        raise HTTPException(status_code=401, detail="Invalid organization")

    plan = org.plan or DEFAULT_PLAN
    limits = PLAN_QUOTAS.get(plan) or PLAN_QUOTAS[DEFAULT_PLAN]

    # 2) Fetch usage for this period (if none yet, allow)
    usage_res = await db.execute(
        select(OrgUsage).where(
            OrgUsage.org_id == org_id,
            OrgUsage.period == period,
        )
    )
    usage = usage_res.scalar_one_or_none()
    if not usage:
        return  # no usage yet → allowed

    # 3) Enforce limits
    if usage.intelligence_runs >= limits["max_runs_per_month"]:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly run quota exceeded for plan '{plan}'",
        )

    if usage.estimated_cost_cents >= limits["max_cost_cents_per_month"]:
        # 402 is okay for "payment required" style gating
        raise HTTPException(
            status_code=402,
            detail=f"Monthly cost quota exceeded for plan '{plan}'",
        )
