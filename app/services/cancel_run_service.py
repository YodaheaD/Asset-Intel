from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_run import IntelligenceRun


TERMINAL_STATUSES = {"completed", "failed", "canceled"}


def normalize_processor_name(name: str) -> str:
    """
    Normalize incoming processor names so your API can accept friendly variants.
    Keep this conservative to avoid accidentally canceling the wrong thing.
    """
    n = (name or "").strip().lower()
    # Allow a couple common aliases
    if n in ("ocr", "ocr_text", "ocr-text"):
        return "ocr-text"
    if n in ("fingerprint", "asset_fingerprint", "asset-fingerprint"):
        return "asset-fingerprint"
    return n


async def request_cancel_run(
    db: AsyncSession,
    *,
    org_id: UUID,
    run_id: UUID,
) -> dict:
    run = (
        await db.execute(
            select(IntelligenceRun).where(
                IntelligenceRun.id == run_id,
                IntelligenceRun.org_id == org_id,
            )
        )
    ).scalar_one_or_none()

    if not run:
        return {"ok": False, "error": "run_not_found"}

    if run.status in TERMINAL_STATUSES:
        return {"ok": True, "already_terminal": True, "status": run.status}

    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(cancel_requested=True)
    )
    await db.commit()

    return {"ok": True, "already_terminal": False, "status": run.status}


async def request_cancel_latest_run_for_asset(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    processor_name: str,
) -> dict:
    """
    Cancel the latest non-terminal run for a given (asset_id, processor_name).
    Returns:
      - ok: bool
      - run_id: str|None
      - status: str|None
      - error: optional
    """
    proc = normalize_processor_name(processor_name)
    if not proc:
        return {"ok": False, "error": "invalid_processor_name"}

    run = (
        await db.execute(
            select(IntelligenceRun)
            .where(
                IntelligenceRun.org_id == org_id,
                IntelligenceRun.asset_id == asset_id,
                IntelligenceRun.processor_name == proc,
                IntelligenceRun.status.not_in(tuple(TERMINAL_STATUSES)),
            )
            .order_by(IntelligenceRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not run:
        return {
            "ok": False,
            "error": "no_active_run_found",
            "run_id": None,
            "status": None,
            "processor_name": proc,
            "asset_id": str(asset_id),
        }

    # If already requested, return idempotently
    if getattr(run, "cancel_requested", False):
        return {
            "ok": True,
            "already_requested": True,
            "run_id": str(run.id),
            "status": run.status,
            "processor_name": proc,
            "asset_id": str(asset_id),
        }

    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run.id)
        .values(cancel_requested=True)
    )
    await db.commit()

    return {
        "ok": True,
        "already_requested": False,
        "run_id": str(run.id),
        "status": run.status,
        "processor_name": proc,
        "asset_id": str(asset_id),
    }


async def is_cancel_requested(
    db: AsyncSession,
    *,
    org_id: UUID,
    run_id: UUID,
) -> bool:
    res = await db.execute(
        select(IntelligenceRun.cancel_requested).where(
            IntelligenceRun.id == run_id,
            IntelligenceRun.org_id == org_id,
        )
    )
    flag = res.scalar_one_or_none()
    return bool(flag)


async def mark_run_canceled(
    db: AsyncSession,
    *,
    org_id: UUID,
    run_id: UUID,
    message: str | None = None,
) -> None:
    await db.execute(
        update(IntelligenceRun)
        .where(
            IntelligenceRun.id == run_id,
            IntelligenceRun.org_id == org_id,
        )
        .values(
            status="canceled",
            canceled_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            progress_message=message or "canceled",
        )
    )
    await db.commit()
