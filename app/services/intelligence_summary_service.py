from __future__ import annotations

from uuid import UUID
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult


def _preview(text: str, max_chars: int = 500) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


async def _latest_result(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    result_type: str,
) -> dict[str, Any] | None:
    """
    Latest completed result of a given type for an asset.
    """
    stmt = (
        select(IntelligenceResult, IntelligenceRun)
        .join(IntelligenceRun, IntelligenceRun.id == IntelligenceResult.run_id)
        .where(
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.status == "completed",
            IntelligenceResult.type == result_type,
        )
        .order_by(IntelligenceRun.completed_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return None

    result, run = row
    return {
        "type": result.type,
        "data": result.data,
        "confidence": result.confidence,
        "run": {
            "id": run.id,
            "processor_name": run.processor_name,
            "processor_version": run.processor_version,
            "status": run.status,
            "completed_at": run.completed_at,
            "estimated_cost_cents": getattr(run, "estimated_cost_cents", 0),
            "input_fingerprint_signature": getattr(run, "input_fingerprint_signature", None),
        },
    }


async def _latest_runs_by_processor(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
) -> dict[str, dict[str, Any]]:
    """
    Returns the latest run per processor_name (any status).
    """
    # Fetch recent runs for this asset (cap to keep it efficient)
    stmt = (
        select(IntelligenceRun)
        .where(
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.asset_id == asset_id,
        )
        .order_by(IntelligenceRun.created_at.desc())
        .limit(50)
    )
    runs = (await db.execute(stmt)).scalars().all()

    latest: dict[str, IntelligenceRun] = {}
    for r in runs:
        if r.processor_name not in latest:
            latest[r.processor_name] = r

    return {
        name: {
            "id": run.id,
            "processor_name": run.processor_name,
            "processor_version": run.processor_version,
            "status": run.status,
            "created_at": run.created_at,
            "completed_at": run.completed_at,
            "error_message": run.error_message,
            "estimated_cost_cents": getattr(run, "estimated_cost_cents", 0),
            "input_fingerprint_signature": getattr(run, "input_fingerprint_signature", None),
        }
        for name, run in latest.items()
    }


async def build_asset_intelligence_summary(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
) -> dict[str, Any]:
    """
    Product-grade summary object for an asset.
    """
    fingerprint = await _latest_result(db, org_id=org_id, asset_id=asset_id, result_type="fingerprint")
    image_metadata = await _latest_result(db, org_id=org_id, asset_id=asset_id, result_type="image_metadata")
    ocr_text = await _latest_result(db, org_id=org_id, asset_id=asset_id, result_type="ocr_text")

    # OCR preview shaping (keep payload small and UI-friendly)
    ocr_preview = None
    if ocr_text and isinstance(ocr_text.get("data"), dict):
        txt = ocr_text["data"].get("text") or ""
        ocr_preview = {
            "preview": _preview(txt, 500),
            "text_length": ocr_text["data"].get("text_length", len(txt)),
            "truncated": ocr_text["data"].get("truncated", False),
            "language": ocr_text["data"].get("language"),
            "method": ocr_text["data"].get("method"),
        }

        # Replace large text blob with preview object in summary
        ocr_text = {
            **ocr_text,
            "data": ocr_preview,
        }

    latest_runs = await _latest_runs_by_processor(db, org_id=org_id, asset_id=asset_id)

    return {
        "asset_id": str(asset_id),
        "latest_runs": latest_runs,
        "latest_results": {
            "fingerprint": fingerprint,
            "image_metadata": image_metadata,
            "ocr_text": ocr_text,
        },
    }
