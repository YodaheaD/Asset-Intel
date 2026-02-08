from __future__ import annotations

import os
from pydantic import BaseModel
class Settings(BaseModel):
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:password@localhost:5432/assetintel",
    )

    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    USE_ARQ_WORKER: bool = os.getenv("USE_ARQ_WORKER", "true").lower() in ("1", "true", "yes")

    # Retry behavior
    ARQ_MAX_TRIES: int = int(os.getenv("ARQ_MAX_TRIES", "3"))

    # Dead-letter list bounds
    DEADLETTER_MAX_ITEMS: int = int(os.getenv("DEADLETTER_MAX_ITEMS", "200"))

    # Admin endpoints (dead-letter view/requeue)
    ADMIN_API_ENABLED: bool = os.getenv("ADMIN_API_ENABLED", "false").lower() in ("1", "true", "yes")
    ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")  # set this in env; required if admin API enabled


    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
