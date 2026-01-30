# app/scripts/create_tables.py
import asyncio

from app.db.base import Base
from app.db.session import engine

# IMPORTANT:
# Every model must be imported so SQLAlchemy registers it in Base.metadata

from app.models.organization import Organization
from app.models.api_key import ApiKey
from app.models.asset import Asset
from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult
from app.models.org_usage import OrgUsage
from app.models.stripe_event import StripeEvent


async def create_all_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(create_all_tables())
