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
from app.services.search_index_service import upsert_ocr_into_index


MAX_TEXT_CHARS = 100_000
MAX_PDF_OCR_PAGES = 3  # keep costs bounded for scanned PDFs
PDF_MIN_TEXT_THRESHOLD = 30  # below this -> treat as "scanned" and try image OCR


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


def _looks_like_pdf(data: bytes) -> bool:
    # PDFs start with "%PDF"
    return data.startswith(b"%PDF")


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extract embedded text from a PDF.
    Fast path (no OCR). Requires `pypdf`.
    """
    try:
        from pypdf import PdfReader
    except Exception as e:
        raise RuntimeError(
            "PDF text extraction requires the 'pypdf' package. "
            f"Import/setup error: {str(e)}"
        )

    reader = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t:
            parts.append(t)

    return "\n".join(parts).strip()


def _ocr_images_from_pdf(pdf_bytes: bytes, lang: str) -> str:
    """
    Rasterize PDF pages -> OCR. Requires:
      - pdf2image (python package)
      - Poppler (system dependency)
      - Pillow + pytesseract + Tesseract (system dependency)
    """
    try:
        from pdf2image import convert_from_bytes
    except Exception as e:
        raise RuntimeError(
            "Scanned-PDF OCR requires 'pdf2image' plus system Poppler. "
            f"Import/setup error: {str(e)}"
        )

    try:
        import pytesseract
    except Exception as e:
        raise RuntimeError(
            "OCR requires pytesseract and system 'tesseract' binary installed. "
            f"Import/setup error: {str(e)}"
        )

    # Convert first N pages to images
    try:
        images = convert_from_bytes(pdf_bytes, first_page=1, last_page=MAX_PDF_OCR_PAGES)
    except Exception as e:
        raise RuntimeError(
            "Failed to rasterize PDF. This often means Poppler is missing or misconfigured. "
            f"Error: {str(e)}"
        )

    texts: list[str] = []
    for i, img in enumerate(images, start=1):
        page_text = pytesseract.image_to_string(img, lang=lang) or ""
        page_text = page_text.strip()
        if page_text:
            texts.append(f"[page {i}]\n{page_text}")

    return "\n\n".join(texts).strip()


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
    resp = requests.get(asset.source_uri, timeout=60)
    resp.raise_for_status()

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].lower()
    raw_bytes = resp.content  # SAFE, seekable via BytesIO

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

    # Case B: PDF (embedded text first, optional scanned-PDF OCR)
    elif content_type == "application/pdf" or _looks_like_pdf(raw_bytes[:8]):
        # Step 1: embedded text
        pdf_text = _extract_pdf_text(raw_bytes)

        if len(pdf_text.strip()) >= PDF_MIN_TEXT_THRESHOLD:
            extracted_text = pdf_text
            extracted_text, truncated = _truncate(extracted_text)
            method = "pdf_text"
        else:
            # Step 2: scanned PDF OCR (optional)
            extracted_text = _ocr_images_from_pdf(raw_bytes, lang=lang)
            extracted_text, truncated = _truncate(extracted_text)
            method = "pdf_image_ocr"

    # Case C: image OR octet-stream that looks like image (Azure Blob)
    elif content_type.startswith("image/") or content_type == "application/octet-stream":
        # Sometimes blob storage returns octet-stream; sniff bytes
        if not _looks_like_image(raw_bytes[:512]):
            # Could still be PDF in octet-stream
            if _looks_like_pdf(raw_bytes[:8]):
                pdf_text = _extract_pdf_text(raw_bytes)
                if len(pdf_text.strip()) >= PDF_MIN_TEXT_THRESHOLD:
                    extracted_text = pdf_text
                    extracted_text, truncated = _truncate(extracted_text)
                    method = "pdf_text"
                else:
                    extracted_text = _ocr_images_from_pdf(raw_bytes, lang=lang)
                    extracted_text, truncated = _truncate(extracted_text)
                    method = "pdf_image_ocr"
            else:
                raise RuntimeError(
                    f"OCR processor could not identify image/PDF content (content-type={content_type})"
                )
        else:
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
        "pdf_ocr_pages": MAX_PDF_OCR_PAGES if method == "pdf_image_ocr" else None,
    }

    # Persist OCR result
    db.add(
        IntelligenceResult(
            org_id=run.org_id,
            asset_id=run.asset_id,
            run_id=run.id,
            type="ocr_text",
            data=data,
            confidence=1.0 if method in ("http_text", "pdf_text") else 0.9,
        )
    )

    # Phase 6.5: Upsert into search index for fast FTS
    await upsert_ocr_into_index(
        db,
        org_id=run.org_id,
        asset_id=run.asset_id,
        ocr_data={"text": extracted_text},
    )

    # Mark completed
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(status="completed", completed_at=datetime.utcnow())
    )
    await db.commit()
