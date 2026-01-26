from fastapi import APIRouter
from app.api.v1 import assets, billing, health, intelligence, intelligence_runs, intelligence_query, payments, stripe_webhook

router = APIRouter()
router.include_router(health.router)
router.include_router(assets.router)
router.include_router(intelligence.router)          # <— required
router.include_router(intelligence_query.router)
router.include_router(intelligence_runs.router)
router.include_router(billing.router, tags=["billing"])
router.include_router(payments.router, tags=["payments"])
router.include_router(stripe_webhook.router, tags=["payments"])