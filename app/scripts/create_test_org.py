import asyncio
import hashlib
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, select

from app.db.session import async_session
from app.models.organization import Organization
from app.models.api_key import ApiKey

# -----------------------------
# Configurable test data
# -----------------------------
TEST_ORG_NAME = "TestOrg"
TEST_API_KEY = "super-secret-api-key"  # Use this in X-API-Key header
TEST_ROLE = "admin"  # owner | admin | member | service

# -----------------------------
# Helper functions
# -----------------------------
def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()

# -----------------------------
# Async main
# -----------------------------
async def main():
    async with async_session() as db:  # type: AsyncSession
        # Check if org exists
        result = await db.execute(select(Organization).where(Organization.name == TEST_ORG_NAME))
        org = result.scalar_one_or_none()

        if not org:
            org = Organization(name=TEST_ORG_NAME)
            db.add(org)
            await db.commit()
            await db.refresh(org)
            print(f"Created test organization: {org.name} (ID: {org.id})")
        else:
            print(f"Test organization already exists: {org.name} (ID: {org.id})")

        # Check if API key exists
        key_hash = hash_key(TEST_API_KEY)
        result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
        existing_key = result.scalar_one_or_none()

        if not existing_key:
            api_key = ApiKey(
                key_hash=key_hash,
                org_id=org.id,
                role=TEST_ROLE,
                is_active=True,
            )
            db.add(api_key)
            await db.commit()
            print(f"Created API key for org '{org.name}': {TEST_API_KEY}")
        else:
            print("API key already exists")

# -----------------------------
# Run the script
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())
