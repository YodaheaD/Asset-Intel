from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

from arq.connections import RedisSettings

from app.core.config import settings
from app.db.session import async_session
from app.services.intelligence_dispatcher import dispatch_run

DEADLETTER_LIST_KEY = "deadletter:intelligence_runs"


def _safe_error_summary(err: str | None, max_len: int = 200) -> str | None:
    if not err:
        return None
    s = str(err).replace("\n", " ").replace("\r", " ").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


async def _push_deadletter_redis(ctx, *, payload: dict) -> None:
    """
    Optional: store dead-letter payload in Redis for quick inspection.
    """
    redis = ctx.get("redis")
    if redis is None:
        return

    await redis.lpush(DEADLETTER_LIST_KEY, json.dumps(payload))
    await redis.ltrim(DEADLETTER_LIST_KEY, 0, settings.DEADLETTER_MAX_ITEMS - 1)


async def _write_deadletter_postgres(
    *,
    run_id: UUID,
    error: str,
    job_try: int,
    task_name: str,
) -> dict:
    """
    Persist deadletter event in Postgres (auditable source of truth).
    """
    from app.models.intelligence_run import IntelligenceRun
    from app.models.deadletter_event import DeadletterEvent
    from sqlalchemy import select, update

    async with async_session() as db:
        run = (
            await db.execute(select(IntelligenceRun).where(IntelligenceRun.id == run_id))
        ).scalar_one_or_none()

        if not run:
            return {"ok": False, "error": "run_not_found"}

        # Mark run failed (dead-lettered)
        await db.execute(
            update(IntelligenceRun)
            .where(IntelligenceRun.id == run_id)
            .values(
                status="failed",
                error_message=f"Dead-lettered after repeated failures: {error}",
                completed_at=datetime.utcnow(),
                progress_message="dead-lettered",
            )
        )

        ev = DeadletterEvent(
            org_id=run.org_id,
            run_id=run.id,
            asset_id=run.asset_id,
            processor_name=run.processor_name,
            processor_version=run.processor_version,
            task_name=task_name,
            job_try=job_try,
            error_summary=_safe_error_summary(error),
            error_raw=error,  # internal/auditable; API will not expose this
            failed_at=datetime.utcnow(),
        )

        db.add(ev)
        await db.commit()

        return {"ok": True, "deadletter_event_id": str(ev.id), "org_id": str(run.org_id)}


async def process_intelligence_run(ctx, run_id: str) -> None:
    """
    ARQ task entrypoint.
    """
    rid = UUID(run_id)

    try:
        async with async_session() as db:
            await dispatch_run(db, rid)

    except Exception as e:
        job_try = int(ctx.get("job_try") or 1)
        max_tries = int(getattr(settings, "ARQ_MAX_TRIES", 3))
        task_name = "process_intelligence_run"
        err = str(e)

        # If last try -> dead-letter (Postgres + optional Redis)
        if job_try >= max_tries:
            # Postgres deadletter event + mark run failed
            pg_res = await _write_deadletter_postgres(
                run_id=rid,
                error=err,
                job_try=job_try,
                task_name=task_name,
            )

            payload = {
                "run_id": run_id,
                "error": err,
                "error_summary": _safe_error_summary(err),
                "failed_at": datetime.utcnow().isoformat() + "Z",
                "job_try": job_try,
                "queue": "arq",
                "task": task_name,
                "postgres": pg_res,
            }

            await _push_deadletter_redis(ctx, payload=payload)
            return

        # Otherwise re-raise to let ARQ retry
        raise


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    functions = [process_intelligence_run]

    max_jobs = 10
    job_timeout = 60 * 10
    max_tries = 3
