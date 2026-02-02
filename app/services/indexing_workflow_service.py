from __future__ import annotations

from uuid import UUID
from datetime import datetime

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_search_index import AssetSearchIndex
from app.models.intelligence_run import IntelligenceRun
from app.services.intelligence_service import enqueue_processor_run
from app.services.ocr_retry_service import should_auto_retry_ocr


async def ensure_asset_indexing(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    background_tasks: BackgroundTasks,
    ensure_fingerprint: bool = True,
    ensure_ocr: bool = True,
) -> dict:
    """
    Ensure the asset has enough indexed data for product endpoints (related/search).

    Returns:
      {
        "indexed": bool,
        "queued": [...],
        "note": str,
        "ocr_failure_category": str|None,
        "ocr_failure_message": str|None,
        "ocr_retry_reason": str|None
      }
    """
    idx = (
        await db.execute(
            select(AssetSearchIndex).where(
                AssetSearchIndex.org_id == org_id,
                AssetSearchIndex.asset_id == asset_id,
            )
        )
    ).scalar_one_or_none()

    has_fp = False
    has_ocr = False
    if idx:
        has_fp = bool(idx.sha256 or idx.etag)
        has_ocr = idx.ocr_tsv is not None

    queued = []

    # 1) Fingerprint first if missing
    if ensure_fingerprint and not has_fp:
        run = await enqueue_processor_run(
            db,
            org_id=org_id,
            asset_id=asset_id,
            processor_name="asset-fingerprint",
            background_tasks=background_tasks,
            force=False,
            retry=False,
        )
        queued.append(
            {
                "processor": run.processor_name,
                "version": run.processor_version,
                "run_id": str(run.id),
                "status": run.status,
            }
        )
        return {
            "indexed": False,
            "queued": queued,
            "note": "Fingerprint indexing started. Retry after completion.",
            "ocr_failure_category": None,
            "ocr_failure_message": None,
            "ocr_retry_reason": None,
        }

    # 2) OCR if missing
    if ensure_ocr and not has_ocr:
        decision = await should_auto_retry_ocr(db, org_id=org_id, asset_id=asset_id)

        # If no OCR run exists, just enqueue normally
        if decision["reason"] == "no_ocr_run_exists":
            run = await enqueue_processor_run(
                db,
                org_id=org_id,
                asset_id=asset_id,
                processor_name="ocr-text",
                background_tasks=background_tasks,
                force=False,
                retry=False,
            )
            queued.append(
                {
                    "processor": run.processor_name,
                    "version": run.processor_version,
                    "run_id": str(run.id),
                    "status": run.status,
                    "auto_retry": False,
                }
            )
            return {
                "indexed": False,
                "queued": queued,
                "note": "OCR indexing started. Retry after completion.",
                "ocr_failure_category": None,
                "ocr_failure_message": None,
                "ocr_retry_reason": None,
            }

        # If latest failed and we should retry, enqueue with retry=True
        if decision["should_retry"]:
            run = await enqueue_processor_run(
                db,
                org_id=org_id,
                asset_id=asset_id,
                processor_name="ocr-text",
                background_tasks=background_tasks,
                force=False,
                retry=True,
            )

            # Ensure ORM instance is fully loaded before mutating (safe pattern)
            await db.refresh(run)
            run.retry_count = (run.retry_count or 0) + 1
            run.last_retry_at = datetime.utcnow()
            await db.commit()

            queued.append(
                {
                    "processor": run.processor_name,
                    "version": run.processor_version,
                    "run_id": str(run.id),
                    "status": run.status,
                    "auto_retry": True,
                    "reason": decision["reason"],
                }
            )
            return {
                "indexed": False,
                "queued": queued,
                "note": "OCR previously failed; auto-retry started. Retry after completion.",
                "ocr_failure_category": decision.get("failure_category"),
                "ocr_failure_message": decision.get("failure_message"),
                "ocr_retry_reason": decision["reason"],
            }

        # Otherwise do not retry; surface classification to caller/UI
        return {
            "indexed": False,
            "queued": [],
            "note": f"OCR not indexed and auto-retry not performed ({decision['reason']}).",
            "ocr_failure_category": decision.get("failure_category"),
            "ocr_failure_message": decision.get("failure_message"),
            "ocr_retry_reason": decision["reason"],
        }

    return {
        "indexed": True,
        "queued": [],
        "note": "Indexing ready.",
        "ocr_failure_category": None,
        "ocr_failure_message": None,
        "ocr_retry_reason": None,
    }
