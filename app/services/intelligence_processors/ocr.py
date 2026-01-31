from __future__ import annotations

from uuid import UUID
from datetime import datetime
import requests
from io import BytesIO

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult


MAX_TEXT_CHARS = 100_000  # prevent huge JSON payloads


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS], True


async def process_ocr_run(db: AsyncSession, run_id: UUID, lang: str = "eng") -> None:
    """
    OCR text extraction.
    - For images: uses pytesseract (requires system tesseract installed)
    - For text/*: returns decoded body as "text extraction"
    - For other types: attempts OCR if it's an image; otherwise fails with a clear error
    """
    # Load run
    run_res = await db.execute(select(IntelligenceRun).where(IntelligenceRun.id == run_id))
    run = run_res.scalar_one()

    # Mark running
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(status="running", error_message=None)
    )
    await db.commit()

    # Load asset
    asset_res = await db.execute(select(Asset).where(Asset.id == run.asset_id))
    asset = asset_res.scalar_one()

    url = asset.source_uri

    # Fetch content (streaming)
    resp = requests.get(url, timeout=45, stream=True)
    resp.raise_for_status()

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()

    extracted_text = ""
    truncated = False
    method = None

    # Case A: text-based content -> return as text extraction
    if content_type.startswith("text/"):
        raw = resp.content
        try:
            extracted_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            extracted_text = raw.decode("latin-1", errors="replace")
        extracted_text, truncated = _truncate(extracted_text)
        method = "http_text"

    # Case B: image -> OCR
    elif content_type in ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/tiff", "image/bmp"):
        try:
            from PIL import Image
            import pytesseract
        except Exception as e:
            raise RuntimeError(
                "OCR requires Pillow + pytesseract and the system 'tesseract' binary installed. "
                f"Import/setup error: {str(e)}"
            )

        img = Image.open(BytesIO(resp.content))
        extracted_text = pytesseract.image_to_string(img, lang=lang) or ""
        extracted_text = extracted_text.strip()
        extracted_text, truncated = _truncate(extracted_text)
        method = "tesseract_ocr"

    else:
        raise RuntimeError(
            f"OCR processor does not support content-type '{content_type}'. "
            "For PDFs, add a PDF extraction path later (Phase 6.x)."
        )

    data = {
        "text": extracted_text,
        "truncated": truncated,
        "content_type": content_type,
        "language": lang,
        "method": method,
        "text_length": len(extracted_text),
    }

    # Persist result
    result = IntelligenceResult(
        org_id=run.org_id,
        asset_id=run.asset_id,
        run_id=run.id,
        type="ocr_text",
        data=data,
        confidence=1.0 if method == "http_text" else 0.9,
    )
    db.add(result)

    # Mark completed
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(status="completed", completed_at=datetime.utcnow())
    )
    await db.commit()
