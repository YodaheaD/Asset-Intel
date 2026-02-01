# app/scripts/create_tables.py
import asyncio

from app.db.base import Base
from app.db.session import engine

# IMPORTANT:
# Every model must be imported so SQLAlchemy registers it in Base.metadata
# models/
# ├─ __init__.py
# ├─ api_key.py
# ├─ asset.py
# ├─ common.py
# ├─ intelligence_result.py
# ├─ intelligence_run.py
# ├─ org_usage.py
# ├─ organization.py
# └─ stripe_event.py
from app.models.organization import Organization
from app.models.api_key import ApiKey
from app.models.asset import Asset
from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult
from app.models.org_usage import OrgUsage
from app.models.stripe_event import StripeEvent

print("Creating database tables...")

async def create_all_tables() -> None:
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("✅ Database tables created successfully!")
    except Exception as e:
        print(f"❌ Failed to create database tables: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(create_all_tables())
