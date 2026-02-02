from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_run import IntelligenceRun
from app.services.fingerprint_signature_service import get_latest_fingerprint_signature


# Tune these
MAX_OCR_RETRIES_PER_SIGNATURE = 2
MIN_RETRY_DELAY_SECONDS = 60


def _looks_like_dependency_missing(msg: str | None) -> bool:
    if not msg:
        return False
    m = msg.lower()
    # common OCR dependency failures
    return (
        "tesseract" in m and ("not found" in m or "no such file" in m or "is not installed" in m)
    ) or ("pytesseract" in m and "import" in m) or ("pillow" in m and "import" in m)


async def should_auto_retry_ocr(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
) -> dict:
    """
    Returns:
      {
        "should_retry": bool,
        "reason": str,
        "current_sig": str|None,
        "latest_ocr_run_id": str|None
      }
    """
    current_sig = await get_latest_fingerprint_signature(db, org_id=org_id, asset_id=asset_id)

    # Find latest OCR run (any status)
    res = await db.execute(
        select(IntelligenceRun)
        .where(
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.processor_name == "ocr-text",
        )
        .order_by(IntelligenceRun.created_at.desc())
        .limit(1)
    )
    run = res.scalar_one_or_none()

    if not run:
        return {
            "should_retry": False,
            "reason": "no_ocr_run_exists",
            "current_sig": current_sig,
            "latest_ocr_run_id": None,
        }

    if run.status != "failed":
        return {
            "should_retry": False,
            "reason": f"latest_ocr_status_{run.status}",
            "current_sig": current_sig,
            "latest_ocr_run_id": str(run.id),
        }

    # Do not retry if failure looks like missing server dependency
    if _looks_like_dependency_missing(run.error_message):
        return {
            "should_retry": False,
            "reason": "dependency_missing_no_retry",
            "current_sig": current_sig,
            "latest_ocr_run_id": str(run.id),
        }

    # Only retry if we have a current signature and it matches the failed run signature.
    # (prevents retrying when the asset changed)
    if current_sig and run.input_fingerprint_signature and current_sig != run.input_fingerprint_signature:
        return {
            "should_retry": False,
            "reason": "asset_changed_signature_mismatch",
            "current_sig": current_sig,
            "latest_ocr_run_id": str(run.id),
        }

    # Rate limit retries
    if run.last_retry_at:
        if datetime.utcnow() - run.last_retry_at < timedelta(seconds=MIN_RETRY_DELAY_SECONDS):
            return {
                "should_retry": False,
                "reason": "retry_rate_limited",
                "current_sig": current_sig,
                "latest_ocr_run_id": str(run.id),
            }

    # Cap retries per signature
    if (run.retry_count or 0) >= MAX_OCR_RETRIES_PER_SIGNATURE:
        return {
            "should_retry": False,
            "reason": "retry_cap_reached",
            "current_sig": current_sig,
            "latest_ocr_run_id": str(run.id),
        }

    return {
        "should_retry": True,
        "reason": "failed_retry_allowed",
        "current_sig": current_sig,
        "latest_ocr_run_id": str(run.id),
    }
