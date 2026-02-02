# app/services/intelligence_processors/ocr.py

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


MAX_TEXT_CHARS = 100_000


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS], True


def _looks_like_image(data: bytes) -> bool:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):  # PNG
        return True
    if data.startswith(b"\xff\xd8\xff"):  # JPEG
        return True
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:  # WEBP
        return True
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):  # TIFF
        return True
    return False


async def process_ocr_run(db: AsyncSession, run_id: UUID, lang: str = "eng") -> None:
    # Load run
    run = (
        await db.execute(
            select(IntelligenceRun).where(IntelligenceRun.id == run_id)
        )
    ).scalar_one()

    # Mark running
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(status="running", error_message=None)
    )
    await db.commit()

    # Load asset
    asset = (
        await db.execute(select(Asset).where(Asset.id == run.asset_id))
    ).scalar_one()

    # Download content ONCE
    resp = requests.get(asset.source_uri, timeout=45)
    resp.raise_for_status()

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].lower()
    raw_bytes = resp.content  # <-- SAFE, seekable via BytesIO

    extracted_text = ""
    truncated = False
    method = None

    # Case A: text content
    if content_type.startswith("text/"):
        try:
            extracted_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            extracted_text = raw_bytes.decode("latin-1", errors="replace")

        extracted_text, truncated = _truncate(extracted_text)
        method = "http_text"

    # Case B: image OR octet-stream that looks like image (Azure Blob)
    elif content_type.startswith("image/") or content_type == "application/octet-stream":
        if not _looks_like_image(raw_bytes[:512]):
            raise RuntimeError(
                f"OCR processor could not identify image content (content-type={content_type})"
            )

        try:
            from PIL import Image
            import pytesseract
        except Exception as e:
            raise RuntimeError(
                "OCR requires Pillow + pytesseract and system 'tesseract' binary installed. "
                f"Import/setup error: {str(e)}"
            )

        img = Image.open(BytesIO(raw_bytes))
        extracted_text = pytesseract.image_to_string(img, lang=lang) or ""
        extracted_text = extracted_text.strip()
        extracted_text, truncated = _truncate(extracted_text)
        method = "tesseract_ocr"

    else:
        raise RuntimeError(
            f"OCR processor does not support content-type '{content_type}'"
        )

    data = {
        "text": extracted_text,
        "truncated": truncated,
        "content_type": content_type,
        "language": lang,
        "method": method,
        "text_length": len(extracted_text),
    }

    db.add(
        IntelligenceResult(
            org_id=run.org_id,
            asset_id=run.asset_id,
            run_id=run.id,
            type="ocr_text",
            data=data,
            confidence=1.0 if method == "http_text" else 0.9,
        )
    )

    # Mark completed
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(status="completed", completed_at=datetime.utcnow())
    )
    await db.commit()
