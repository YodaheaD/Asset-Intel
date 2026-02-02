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
        }

    # 2) OCR if missing
    if ensure_ocr and not has_ocr:
        # Check auto-retry logic
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

            # bump retry metadata on the NEW run (so it carries the cap state forward)
            await db.execute(
                select(IntelligenceRun).where(IntelligenceRun.id == run.id)
            )
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
            }

        # Otherwise do not retry, return reason
        return {
            "indexed": False,
            "queued": [],
            "note": f"OCR not indexed and auto-retry not performed ({decision['reason']}).",
            "ocr_retry_reason": decision["reason"],
        }

    return {
        "indexed": True,
        "queued": [],
    }
