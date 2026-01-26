from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stripe_event import StripeEvent


async def already_processed(db: AsyncSession, stripe_event_id: str) -> bool:
    res = await db.execute(
        select(StripeEvent).where(StripeEvent.stripe_event_id == stripe_event_id)
    )
    return res.scalar_one_or_none() is not None


async def mark_processed(db: AsyncSession, stripe_event_id: str, event_type: str) -> None:
    db.add(StripeEvent(stripe_event_id=stripe_event_id, event_type=event_type))
    await db.commit()
