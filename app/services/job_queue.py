from __future__ import annotations

import asyncio
from typing import Any, Optional
from uuid import UUID

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

TASK_PROCESS_RUN = "process_intelligence_run"

_redis_pool: Optional[ArqRedis] = None
_pool_lock = asyncio.Lock()


async def init_redis_pool() -> ArqRedis:
    global _redis_pool
    async with _pool_lock:
        if _redis_pool is None:
            _redis_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        return _redis_pool


async def get_redis_pool() -> ArqRedis:
    if _redis_pool is None:
        return await init_redis_pool()
    return _redis_pool


async def close_redis_pool() -> None:
    global _redis_pool
    async with _pool_lock:
        if _redis_pool is None:
            return

        pool = _redis_pool
        _redis_pool = None

        # redis asyncio in your version: close is async
        if hasattr(pool, "aclose"):
            await pool.aclose()  # type: ignore[attr-defined]
        else:
            await pool.close()  # type: ignore[func-returns-value]

        try:
            cp = getattr(pool, "connection_pool", None)
            if cp is not None and hasattr(cp, "disconnect"):
                res = cp.disconnect()
                if asyncio.iscoroutine(res):
                    await res
        except Exception:
            pass


async def enqueue_process_run(run_id: UUID) -> dict[str, Any]:
    """
    Enqueue a run to be processed by the ARQ worker.

    IMPORTANT:
    We do NOT pass _queue_name here. That uses ARQ's default queue key and
    avoids queue-name mismatch problems.
    """
    redis = await get_redis_pool()
    job = await redis.enqueue_job(TASK_PROCESS_RUN, str(run_id))

    return {
        "queued": True,
        "queue": "arq",
        "job_id": job.job_id if job else None,
    }
