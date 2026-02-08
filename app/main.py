from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI

# Import all models to populate Base.metadata
from app.models.organization import Organization
from app.models.api_key import ApiKey
from app.models.asset import Asset

from app.api.v1.router import router as api_router
from app.services.job_queue import init_redis_pool, close_redis_pool
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    if settings.USE_ARQ_WORKER:
        await init_redis_pool()

    yield

    # Shutdown
    if settings.USE_ARQ_WORKER:
        await close_redis_pool()


app = FastAPI(title="AssetIntel API", lifespan=lifespan)

app.include_router(api_router, prefix="/api/v1")
