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


async def _cascade_cancel_asset_runs(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    exclude_run_id: UUID | None = None,
    processors: list[str] | None = None,
) -> dict:
    """
    Mark cancel_requested for any active runs for this asset (optionally filtered by processor).
    Returns counts and run_ids canceled.
    """
    q = select(IntelligenceRun).where(
        IntelligenceRun.org_id == org_id,
        IntelligenceRun.asset_id == asset_id,
        IntelligenceRun.status.not_in(tuple(TERMINAL_STATUSES)),
    )

    if processors:
        q = q.where(IntelligenceRun.processor_name.in_(processors))

    q = q.order_by(IntelligenceRun.created_at.desc()).limit(50)

    runs = (await db.execute(q)).scalars().all()

    canceled_ids: list[str] = []
    for r in runs:
        if exclude_run_id and r.id == exclude_run_id:
            continue
        if getattr(r, "cancel_requested", False):
            continue
        canceled_ids.append(str(r.id))

    if not canceled_ids:
        return {"cascaded": False, "canceled_run_ids": [], "count": 0}

    # Single UPDATE for all selected run IDs
    await db.execute(
        update(IntelligenceRun)
        .where(
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.id.in_([UUID(x) for x in canceled_ids]),
        )
        .values(cancel_requested=True)
    )
    await db.commit()

    return {"cascaded": True, "canceled_run_ids": canceled_ids, "count": len(canceled_ids)}


async def request_cancel_latest_run_for_asset(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    processor_name: str,
    cascade: bool = True,
) -> dict:
    """
    Cancel the latest non-terminal run for a given (asset_id, processor_name).
    Optionally cascade cancellation to other dependent runs.

    Cascades:
      - If canceling asset-fingerprint and cascade=True:
          cancel active ocr-text runs (and optionally other processors later)
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
            "cascade": cascade,
        }

    # Idempotent: if already requested, still allow cascade to be applied
    already_requested = bool(getattr(run, "cancel_requested", False))

    if not already_requested:
        await db.execute(
            update(IntelligenceRun)
            .where(IntelligenceRun.id == run.id)
            .values(cancel_requested=True)
        )
        await db.commit()

    cascade_info = {"cascaded": False, "canceled_run_ids": [], "count": 0}

    if cascade:
        # Only fingerprint cancellation cascades by default
        if proc == "asset-fingerprint":
            cascade_info = await _cascade_cancel_asset_runs(
                db,
                org_id=org_id,
                asset_id=asset_id,
                exclude_run_id=run.id,
                processors=["ocr-text"],
            )

    return {
        "ok": True,
        "already_requested": already_requested,
        "run_id": str(run.id),
        "status": run.status,
        "processor_name": proc,
        "asset_id": str(asset_id),
        "cascade": cascade,
        "cascade_result": cascade_info,
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
