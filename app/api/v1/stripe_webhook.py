# app/api/v1/stripe_webhook.py

import stripe
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import get_async_db
from app.core.stripe_config import STRIPE_WEBHOOK_SECRET
from app.models.organization import Organization
from app.models.stripe_event import StripeEvent

router = APIRouter()


def _plan_from_price_id(price_id: str | None) -> str:
    """
    Map Stripe price.id -> internal plan string.
    Keep this mapping centralized and explicit.
    """
    if not price_id:
        return "free"

    # Update these to match your Stripe Price IDs
    PRICE_TO_PLAN = {
        "price_1StePHCLBwfeKb63X4C6P3nU": "pro",
        "price_1SteQeCLBwfeKb639PqgBLAp": "team",
    }
    return PRICE_TO_PLAN.get(price_id, "free")


async def _find_org(
    db: AsyncSession,
    customer_id: str | None,
    org_id_meta: str | None,
) -> Organization | None:
    """
    Resolve an Organization using either metadata.org_id (preferred) or Stripe customer_id.
    """
    if org_id_meta:
        try:
            org_res = await db.execute(
                select(Organization).where(Organization.id == org_id_meta)
            )
            org = org_res.scalar_one_or_none()
            if org:
                return org
        except Exception:
            # If org_id_meta is malformed, fall through to customer lookup
            pass

    if customer_id:
        org_res = await db.execute(
            select(Organization).where(Organization.stripe_customer_id == customer_id)
        )
        return org_res.scalar_one_or_none()

    return None


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid webhook signature: {str(e)}")

    event_id = event["id"]
    event_type = event["type"]
    event_created = int(event.get("created", 0))

    # Extract customer_id + (optional) plan + (optional) subscription_id + metadata org_id
    customer_id: str | None = None
    new_plan: str | None = None
    subscription_id: str | None = None
    org_id_meta: str | None = None

    # Handle Checkout completion (useful for binding org <-> subscription reliably)
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        org_id_meta = (session.get("metadata") or {}).get("org_id")
        # We generally don't set plan here; subscription events will reflect the price -> plan mapping

    # Subscription create/update => determine plan from price
    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        sub = event["data"]["object"]
        customer_id = sub.get("customer")
        subscription_id = sub.get("id")

        items = sub.get("items", {}).get("data", [])
        price_id = None
        if items and items[0].get("price"):
            price_id = items[0]["price"].get("id")

        new_plan = _plan_from_price_id(price_id)

    # Subscription deleted => downgrade
    elif event_type == "customer.subscription.deleted":
        sub = event["data"]["object"]
        customer_id = sub.get("customer")
        subscription_id = sub.get("id")
        new_plan = "free"

    # Payment lifecycle events (optional gating; currently we just store subscription_id if present)
    elif event_type == "invoice.paid":
        inv = event["data"]["object"]
        customer_id = inv.get("customer")
        subscription_id = inv.get("subscription")

    elif event_type == "invoice.payment_failed":
        inv = event["data"]["object"]
        customer_id = inv.get("customer")
        subscription_id = inv.get("subscription")
        # Optional: set restrictive plan_status later; for now, do not change org.plan here.

    else:
        # Ignore unhandled events but acknowledge to Stripe
        return {"status": "ok", "ignored": True}

    # For handled events, we need a customer_id or metadata org_id to locate an org
    if not customer_id and not org_id_meta:
        return {"status": "ok", "ignored": True}

    # Atomic + idempotent transaction:
    # - Insert StripeEvent first (unique stripe_event_id acts like a lock)
    # - Update org plan only if event is newer than last applied
    try:
        async with db.begin():
            # 1) Insert idempotency record FIRST (flush triggers UNIQUE constraint)
            db.add(
                StripeEvent(
                    stripe_event_id=event_id,
                    event_type=event_type,
                    stripe_event_created=event_created,
                )
            )
            await db.flush()

            # 2) Locate org (metadata org_id preferred)
            org = await _find_org(db, customer_id, org_id_meta)

            # If org not found, keep StripeEvent row so we don't reprocess forever
            if not org:
                return {"status": "ok", "org_found": False}

            # 3) Out-of-order protection:
            # Only apply state updates if this event is NEWER than the last applied event
            last = org.stripe_last_event_created or 0
            if event_created > last:
                # Always store latest seen subscription id if present
                if subscription_id:
                    org.stripe_subscription_id = subscription_id

                # Apply plan change only if we have one for this event type
                if new_plan is not None:
                    org.plan = new_plan

                org.stripe_last_event_created = event_created
            # else: ignore older event (but still recorded as processed)

    except IntegrityError:
        # stripe_event_id already exists => duplicate delivery => idempotent OK
        return {"status": "ok", "idempotent": True}

    except Exception as e:
        # Rollback is automatic with db.begin() on exception; Stripe will retry
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")

    return {"status": "ok", "idempotent": False}
