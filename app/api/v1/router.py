from fastapi import APIRouter
from app.api.v1 import assets, billing, health, intelligence, intelligence_runs, intelligence_query, payments, stripe_webhook, intelligence_summary, search, related_assets, index_status, run_status, cancel_run, admin_deadletter

router = APIRouter()
router.include_router(health.router)
router.include_router(assets.router)
router.include_router(intelligence.router)          # <— required
router.include_router(intelligence_query.router)
router.include_router(intelligence_runs.router)
router.include_router(billing.router, tags=["billing"])
router.include_router(payments.router, tags=["payments"])
router.include_router(stripe_webhook.router, tags=["payments"])
router.include_router(intelligence_summary.router, tags=["intelligence"])
router.include_router(search.router, tags=["search"])
router.include_router(related_assets.router, tags=["search"])
router.include_router(index_status.router, tags=["search"])
router.include_router(run_status.router, tags=["intelligence"])
router.include_router(cancel_run.router, tags=["intelligence"])

# Admin
router.include_router(admin_deadletter.router, tags=["admin"])