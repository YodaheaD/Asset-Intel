import os
import stripe
from dotenv import load_dotenv
load_dotenv()

STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

stripe.api_key = STRIPE_API_KEY

# Map internal plans → Stripe Price IDs
PLAN_PRICE_IDS = {
    "free": None,
    "pro": "price_1StePHCLBwfeKb63X4C6P3nU",
    "team": "price_1SteQeCLBwfeKb639PqgBLAp",
}
