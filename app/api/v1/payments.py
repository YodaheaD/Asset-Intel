from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import stripe

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.models.organization import Organization
from app.core.stripe_config import PLAN_PRICE_IDS
from app.services.stripe_service import create_customer, ensure_test_default_payment_method

router = APIRouter()


# @router.post("/billing/upgrade")
# async def upgrade_plan(
#     plan: str = Query(..., description="Target plan: pro/team"),
#     db: AsyncSession = Depends(get_async_db),
#     org_id=Depends(get_current_org_id),
# ):
#     # Validate plan
#     if plan not in PLAN_PRICE_IDS or plan == "free":
#         raise HTTPException(status_code=400, detail="Invalid plan")

#     price_id = PLAN_PRICE_IDS.get(plan)
#     if not price_id:
#         raise HTTPException(status_code=400, detail="Missing Stripe price for plan")

#     # Load org
#     org_res = await db.execute(select(Organization).where(Organization.id == org_id))
#     org = org_res.scalar_one_or_none()
#     if not org:
#         raise HTTPException(status_code=404, detail="Organization not found")

#     # Create Stripe customer if needed
#     if not org.stripe_customer_id:
#         customer_id = create_customer(org.name)
#         org.stripe_customer_id = customer_id
#         await db.commit()
#         await db.refresh(org)

#     customer_id = org.stripe_customer_id

#     # TEST MODE helper: ensure a default PM exists so Subscription creation doesn't fail
#     # (In production, you'd use Checkout or Customer Portal instead of this.)
#     #ensure_test_default_payment_method(customer_id)
#     pm_id = ensure_test_default_payment_method(customer_id)
#     print("Set default payment method:", pm_id, "for customer:", customer_id)
#     try:
#         # Create subscription
#         # payment_behavior=default_incomplete is safer while you’re still wiring flows
#         sub = stripe.Subscription.create(
#             customer=customer_id,
#             items=[{"price": price_id}],
#             payment_behavior="default_incomplete",
#             expand=["latest_invoice.payment_intent"],
#         )
#     except stripe.error.StripeError as e:
#         # Surface Stripe error cleanly
#         raise HTTPException(status_code=500, detail=str(e))

#     # IMPORTANT: In a webhook-driven system, you should NOT set org.plan here.
#     # Let webhooks update it authoritatively.
#     # But we can return subscription details for debugging.
#     latest_invoice = sub.get("latest_invoice") or {}
#     payment_intent = latest_invoice.get("payment_intent") or {}

#     return {
#         "status": "subscription_created",
#         "org_id": str(org.id),
#         "stripe_customer_id": customer_id,
#         "subscription_id": sub.get("id"),
#         "plan_requested": plan,
#         "latest_invoice_id": latest_invoice.get("id"),
#         "payment_intent_id": payment_intent.get("id"),
#         "payment_intent_status": payment_intent.get("status"),
#     }



# Put these in env in real deploy
CHECKOUT_SUCCESS_URL = "http://localhost:3000/billing/success"
CHECKOUT_CANCEL_URL = "http://localhost:3000/billing/cancel"
PORTAL_RETURN_URL = "http://localhost:3000/billing"


@router.post("/billing/checkout")
async def create_checkout_session(
    plan: str,
    db: AsyncSession = Depends(get_async_db),
    org_id = Depends(get_current_org_id),
):
    price_id = PLAN_PRICE_IDS.get(plan)
    if not price_id:
        raise HTTPException(status_code=400, detail="Invalid plan for checkout")

    org_res = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_res.scalar_one()

    # Create Stripe customer if missing
    if not org.stripe_customer_id:
        customer = stripe.Customer.create(
            name=org.name,
            metadata={"org_id": str(org.id)},
        )
        org.stripe_customer_id = customer.id
        await db.commit()

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=org.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=CHECKOUT_SUCCESS_URL,
        cancel_url=CHECKOUT_CANCEL_URL,
        # Helps map webhook events back to org even if customer metadata changes
        metadata={"org_id": str(org.id), "target_plan": plan},
    )

    return {"checkout_url": session.url}


@router.post("/billing/portal")
async def create_customer_portal_session(
    db: AsyncSession = Depends(get_async_db),
    org_id = Depends(get_current_org_id),
):
    org_res = await db.execute(select(Organization).where(Organization.id == org_id))
    org = org_res.scalar_one()

    if not org.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer for org")

    portal = stripe.billing_portal.Session.create(
        customer=org.stripe_customer_id,
        return_url=PORTAL_RETURN_URL,
    )
    return {"portal_url": portal.url}

