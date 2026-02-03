from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_run import IntelligenceRun
from app.services.fingerprint_signature_service import get_latest_fingerprint_signature


MAX_OCR_RETRIES_PER_SIGNATURE = 2
MIN_RETRY_DELAY_SECONDS = 60


def classify_ocr_failure(error_message: str | None) -> dict:
    """
    Returns:
      { "category": str|None, "message": str|None }

    Stable categories for UI:
      - dependency_missing
      - unsupported_content_type
      - not_image
      - network_error
      - http_error
      - pdf_dependency_missing
      - pdf_rasterize_failed
      - unknown
    """
    if not error_message:
        return {"category": None, "message": None}

    msg = str(error_message)
    m = msg.lower()

    # PDF-specific dependency issues
    if "pdf2image" in m and ("requires" in m or "import" in m):
        return {"category": "pdf_dependency_missing", "message": msg}
    if "poppler" in m and ("missing" in m or "not found" in m or "unable" in m or "failed" in m):
        return {"category": "pdf_dependency_missing", "message": msg}
    if "rasterize pdf" in m or "failed to rasterize pdf" in m:
        return {"category": "pdf_rasterize_failed", "message": msg}

    # Dependency problems (tesseract/pytesseract/pillow)
    if (
        ("tesseract" in m and ("not found" in m or "no such file" in m or "is not installed" in m))
        or ("pytesseract" in m and "import" in m)
        or ("pillow" in m and "import" in m)
        or ("tesseract" in m and "executable" in m)
    ):
        return {"category": "dependency_missing", "message": msg}

    # Unsupported content type
    if "does not support content-type" in m or "does not support content type" in m:
        return {"category": "unsupported_content_type", "message": msg}

    # Not an image / could not identify image content
    if "could not identify image" in m or "identify image content" in m or "not an image" in m:
        return {"category": "not_image", "message": msg}

    # Network issues
    if any(x in m for x in ["timed out", "timeout", "connection", "dns", "name or service not known", "failed to establish a new connection"]):
        return {"category": "network_error", "message": msg}

    # HTTP-ish errors
    if any(x in m for x in ["404", "403", "401", "500", "502", "503", "504", "httperror"]):
        return {"category": "http_error", "message": msg}

    return {"category": "unknown", "message": msg}


def _looks_like_dependency_missing(msg: str | None) -> bool:
    c = classify_ocr_failure(msg)
    return c["category"] in ("dependency_missing", "pdf_dependency_missing")


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
        "latest_ocr_run_id": str|None,
        "failure_category": str|None,
        "failure_message": str|None,
      }
    """
    current_sig = await get_latest_fingerprint_signature(db, org_id=org_id, asset_id=asset_id)

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
            "failure_category": None,
            "failure_message": None,
        }

    failure = classify_ocr_failure(run.error_message)

    if run.status != "failed":
        return {
            "should_retry": False,
            "reason": f"latest_ocr_status_{run.status}",
            "current_sig": current_sig,
            "latest_ocr_run_id": str(run.id),
            "failure_category": failure["category"],
            "failure_message": failure["message"],
        }

    # Do not retry if failure is dependency-related (tesseract/poppler/pdf2image missing)
    if _looks_like_dependency_missing(run.error_message):
        return {
            "should_retry": False,
            "reason": "dependency_missing_no_retry",
            "current_sig": current_sig,
            "latest_ocr_run_id": str(run.id),
            "failure_category": failure["category"],
            "failure_message": failure["message"],
        }

    if current_sig and run.input_fingerprint_signature and current_sig != run.input_fingerprint_signature:
        return {
            "should_retry": False,
            "reason": "asset_changed_signature_mismatch",
            "current_sig": current_sig,
            "latest_ocr_run_id": str(run.id),
            "failure_category": failure["category"],
            "failure_message": failure["message"],
        }

    if run.last_retry_at:
        if datetime.utcnow() - run.last_retry_at < timedelta(seconds=MIN_RETRY_DELAY_SECONDS):
            return {
                "should_retry": False,
                "reason": "retry_rate_limited",
                "current_sig": current_sig,
                "latest_ocr_run_id": str(run.id),
                "failure_category": failure["category"],
                "failure_message": failure["message"],
            }

    if (run.retry_count or 0) >= MAX_OCR_RETRIES_PER_SIGNATURE:
        return {
            "should_retry": False,
            "reason": "retry_cap_reached",
            "current_sig": current_sig,
            "latest_ocr_run_id": str(run.id),
            "failure_category": failure["category"],
            "failure_message": failure["message"],
        }

    return {
        "should_retry": True,
        "reason": "failed_retry_allowed",
        "current_sig": current_sig,
        "latest_ocr_run_id": str(run.id),
        "failure_category": failure["category"],
        "failure_message": failure["message"],
    }
