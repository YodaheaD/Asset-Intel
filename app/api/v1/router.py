from fastapi import APIRouter
from app.api.v1 import assets, billing, health, intelligence, intelligence_runs, intelligence_query

router = APIRouter()
router.include_router(health.router)
router.include_router(assets.router)
router.include_router(intelligence.router)          # <— required
router.include_router(intelligence_query.router)
router.include_router(intelligence_runs.router)
router.include_router(billing.router, tags=["billing"])
