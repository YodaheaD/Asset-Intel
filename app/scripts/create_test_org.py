# app/scripts/create_test_org.py
import asyncio
import hashlib

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

# -----------------------------
# Async main
# -----------------------------
async def main() -> None:
    async with async_session() as db:  # type: AsyncSession

        # -----------------------------
        # Ensure organization exists
        # -----------------------------
        result = await db.execute(
            select(Organization).where(Organization.name == TEST_ORG_NAME)
        )
        org = result.scalar_one_or_none()

        if not org:
            org = Organization(name=TEST_ORG_NAME)
            db.add(org)
            await db.commit()
            await db.refresh(org)
            print(f"✅ Created test organization: {org.name} (ID: {org.id})")
        else:
            print(f"ℹ️ Organization already exists: {org.name} (ID: {org.id})")

        # -----------------------------
        # Ensure API key exists
        # -----------------------------
        key_hash = hash_key(TEST_API_KEY)

        result = await db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
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
            print(f"✅ Created API key for org '{org.name}'")
            print(f"   → Raw key (store securely): {TEST_API_KEY}")
        else:
            print("ℹ️ API key already exists (no changes made)")

# -----------------------------
# Run the script
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())
