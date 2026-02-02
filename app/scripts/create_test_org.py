# app/scripts/create_test_org.py

import asyncio
import hashlib
from typing import Any

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

# Billing / plan defaults
TEST_PLAN = "free"  # free | pro | team
TEST_STRIPE_CUSTOMER_ID = None
TEST_STRIPE_SUBSCRIPTION_ID = None

# -----------------------------
# Helper functions
# -----------------------------
def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def set_if_exists(obj: Any, field: str, value: Any) -> None:
    """
    Future-proof helper:
    Only sets ORM fields that exist on the model.
    Prevents this script from breaking when models evolve.
    """
    if hasattr(obj, field):
        setattr(obj, field, value)


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

            # Billing-related defaults (safe setters)
            set_if_exists(org, "plan", TEST_PLAN)
            set_if_exists(org, "stripe_customer_id", TEST_STRIPE_CUSTOMER_ID)
            set_if_exists(org, "stripe_subscription_id", TEST_STRIPE_SUBSCRIPTION_ID)
            set_if_exists(org, "stripe_last_event_created", None)

            db.add(org)
            await db.commit()
            await db.refresh(org)

            print(f"✅ Created test organization: {org.name}")
            print(f"   → id: {org.id}")
        else:
            # Keep org aligned with current defaults if schema changed
            set_if_exists(org, "plan", TEST_PLAN)
            set_if_exists(org, "stripe_customer_id", TEST_STRIPE_CUSTOMER_ID)
            set_if_exists(org, "stripe_subscription_id", TEST_STRIPE_SUBSCRIPTION_ID)

            await db.commit()

            print(f"ℹ️ Organization already exists: {org.name}")
            print(f"   → id: {org.id}")
            if hasattr(org, "plan"):
                print(f"   → plan: {org.plan}")

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

            print("✅ Created API key")
            print(f"   → org: {org.name}")
            print(f"   → role: {TEST_ROLE}")
            print(f"   → raw key (store securely): {TEST_API_KEY}")
        else:
            print("ℹ️ API key already exists")
            print(f"   → raw key (use in X-API-Key): {TEST_API_KEY}")


# -----------------------------
# Run the script
# -----------------------------
if __name__ == "__main__":
    asyncio.run(main())
