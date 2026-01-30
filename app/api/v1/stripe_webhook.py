import stripe
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_async_db
from app.core.stripe_config import STRIPE_WEBHOOK_SECRET
from app.models.organization import Organization
from app.services.stripe_webhook_service import already_processed, mark_processed

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


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        print(" using webhook secret:", STRIPE_WEBHOOK_SECRET)
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET,
        )
    except Exception as e:
        print("Webhook signature verification failed:", str(e))
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_id = event["id"]
    event_type = event["type"]

    # 1) Idempotency check: if we've processed this event, do nothing
    if await already_processed(db, event_id):
        return {"status": "ok", "idempotent": True}

    # 2) Process event (plan changes)
    try:
        if event_type in (
            "customer.subscription.created",
            "customer.subscription.updated",
        ):
            sub = event["data"]["object"]
            customer_id = sub["customer"]

            # price id can be nested; safe default -> free
            items = sub.get("items", {}).get("data", [])
            price_id = None
            if items and items[0].get("price"):
                price_id = items[0]["price"].get("id")

            new_plan = _plan_from_price_id(price_id)

            org_res = await db.execute(
                select(Organization).where(Organization.stripe_customer_id == customer_id)
            )
            org = org_res.scalar_one_or_none()
            if org:
                org.plan = new_plan
                await db.commit()

        elif event_type == "customer.subscription.deleted":
            sub = event["data"]["object"]
            customer_id = sub["customer"]

            org_res = await db.execute(
                select(Organization).where(Organization.stripe_customer_id == customer_id)
            )
            org = org_res.scalar_one_or_none()
            if org:
                org.plan = "free"
                await db.commit()

        # (Optional) You can add invoice.payment_failed or invoice.paid later

    except Exception as e:
        # If we fail processing, DO NOT mark processed; Stripe will retry.
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")

    # 3) Mark processed ONLY after successful processing
    await mark_processed(db, event_id, event_type)

    return {"status": "ok", "idempotent": False}