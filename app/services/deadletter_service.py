from __future__ import annotations

from datetime import datetime
from uuid import UUID
from typing import Any

from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deadletter_event import DeadletterEvent
from app.models.intelligence_run import IntelligenceRun
from app.services.job_queue import enqueue_process_run
from app.services.cancel_run_service import normalize_processor_name


def _safe_error_summary(err: str | None, max_len: int = 200) -> str | None:
    if not err:
        return None
    s = str(err).replace("\n", " ").replace("\r", " ").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


async def list_deadletters_for_org(
    db: AsyncSession,
    *,
    org_id: UUID,
    limit: int = 50,
) -> dict[str, Any]:
    """
    List latest deadletter events for this org (safe payload).
    No raw stack traces: only error_summary.
    """
    events = (
        await db.execute(
            select(DeadletterEvent)
            .where(DeadletterEvent.org_id == org_id)
            .order_by(desc(DeadletterEvent.failed_at))
            .limit(limit)
        )
    ).scalars().all()

    items: list[dict[str, Any]] = []
    for ev in events:
        items.append(
            {
                "id": str(ev.id),
                "run_id": str(ev.run_id),
                "asset_id": str(ev.asset_id),
                "processor_name": ev.processor_name,
                "processor_version": ev.processor_version,
                "task_name": ev.task_name,
                "job_try": ev.job_try,
                "failed_at": ev.failed_at,
                "requeued_at": ev.requeued_at,
                "error_summary": ev.error_summary,
            }
        )

    return {"items": items, "count": len(items)}


async def requeue_deadletter_run(
    db: AsyncSession,
    *,
    org_id: UUID,
    run_id: UUID,
) -> dict[str, Any]:
    """
    Requeue a dead-lettered run:
      - verify run belongs to org_id
      - mark latest deadletter event for run_id as requeued_at
      - reset run to pending
      - enqueue to ARQ
    """
    run = (
        await db.execute(
            select(IntelligenceRun).where(
                IntelligenceRun.id == run_id,
                IntelligenceRun.org_id == org_id,
            )
        )
    ).scalar_one_or_none()

    if not run:
        return {"ok": False, "error": "run_not_found_or_wrong_org"}

    # Mark requeued_at for the newest deadletter event for this run (if exists)
    ev = (
        await db.execute(
            select(DeadletterEvent)
            .where(
                DeadletterEvent.org_id == org_id,
                DeadletterEvent.run_id == run_id,
                DeadletterEvent.requeued_at.is_(None),
            )
            .order_by(desc(DeadletterEvent.failed_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if ev:
        ev.requeued_at = datetime.utcnow()

    # Reset run state for retry
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(
            status="pending",
            error_message=None,
            completed_at=None,
            progress_current=0,
            progress_total=None,
            progress_message="requeued",
            cancel_requested=False,
            canceled_at=None,
        )
    )
    await db.commit()

    enqueue_info = await enqueue_process_run(run_id)

    return {
        "ok": True,
        "run_id": str(run_id),
        "deadletter_event_id": (str(ev.id) if ev else None),
        "enqueue": enqueue_info,
    }


async def requeue_latest_deadletter_for_asset(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    processor_name: str = "ocr-text",
) -> dict[str, Any]:
    """
    Requeue the latest dead-lettered run for a given asset + processor.
    Default processor is OCR since that's the common case.
    """
    proc = normalize_processor_name(processor_name)
    if not proc:
        return {"ok": False, "error": "invalid_processor_name"}

    # Find latest deadletter event for asset+proc that hasn't been requeued
    ev = (
        await db.execute(
            select(DeadletterEvent)
            .where(
                DeadletterEvent.org_id == org_id,
                DeadletterEvent.asset_id == asset_id,
                DeadletterEvent.processor_name == proc,
                DeadletterEvent.requeued_at.is_(None),
            )
            .order_by(desc(DeadletterEvent.failed_at))
            .limit(1)
        )
    ).scalar_one_or_none()

    if not ev:
        return {
            "ok": False,
            "error": "no_deadletter_found",
            "asset_id": str(asset_id),
            "processor_name": proc,
        }

    # Requeue by run_id
    return await requeue_deadletter_run(db, org_id=org_id, run_id=ev.run_id)
