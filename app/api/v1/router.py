from fastapi import APIRouter
from app.api.v1 import assets, health

router = APIRouter()
router.include_router(health.router)
router.include_router(assets.router)
