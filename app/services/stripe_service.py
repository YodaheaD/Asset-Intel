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


def ensure_test_default_payment_method(customer_id: str) -> str:
    """
    Test-mode helper.
    Ensures the customer has at least one attached card PaymentMethod and sets it as default.
    Returns the attached payment_method_id.
    """

    # 1) See if customer already has an attached card PM
    pms = stripe.PaymentMethod.list(customer=customer_id, type="card")
    if pms.data:
        pm_id = pms.data[0].id
        stripe.Customer.modify(
            customer_id,
            invoice_settings={"default_payment_method": pm_id},
        )
        return pm_id

    # 2) Attach a known test PM (Stripe will return a concrete pm_... id)
    attached = stripe.PaymentMethod.attach("pm_card_visa", customer=customer_id)
    pm_id = attached.id  # <-- IMPORTANT: use returned id, not "pm_card_visa"

    # 3) Set as default
    stripe.Customer.modify(
        customer_id,
        invoice_settings={"default_payment_method": pm_id},
    )

    return pm_id