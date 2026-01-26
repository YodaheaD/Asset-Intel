import stripe
from app.core.stripe_config import PLAN_PRICE_IDS


def create_customer(org_name: str) -> str:
    customer = stripe.Customer.create(
        name=org_name,
    )
    return customer.id


def create_subscription(customer_id: str, plan: str) -> str:
    price_id = PLAN_PRICE_IDS.get(plan)
    if not price_id:
        raise ValueError("Invalid or free plan")

    subscription = stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": price_id}],
    )
    return subscription.id
