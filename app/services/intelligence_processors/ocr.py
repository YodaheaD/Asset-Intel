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
from app.services.cancel_run_service import is_cancel_requested, mark_run_canceled


MAX_TEXT_CHARS = 100_000
MAX_PDF_OCR_PAGES = 3
PDF_MIN_TEXT_THRESHOLD = 30


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS], True


def _looks_like_image(data: bytes) -> bool:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if data.startswith(b"\xff\xd8\xff"):
        return True
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return True
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
        return True
    return False


def _looks_like_pdf(data: bytes) -> bool:
    return data.startswith(b"%PDF")


def _extract_pdf_text(pdf_bytes: bytes) -> str:
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


async def _upsert_partial_result(
    db: AsyncSession,
    *,
    run: IntelligenceRun,
    pages_completed: int,
    pages_total: int,
    text_partial: str,
) -> None:
    partial_text, _ = _truncate(text_partial)

    existing = (
        await db.execute(
            select(IntelligenceResult).where(
                IntelligenceResult.run_id == run.id,
                IntelligenceResult.type == "ocr_text_partial",
            )
        )
    ).scalar_one_or_none()

    payload = {
        "pages_completed": pages_completed,
        "pages_total": pages_total,
        "text_partial": partial_text,
    }

    if existing:
        existing.data = payload
        existing.confidence = 0.85
    else:
        db.add(
            IntelligenceResult(
                org_id=run.org_id,
                asset_id=run.asset_id,
                run_id=run.id,
                type="ocr_text_partial",
                data=payload,
                confidence=0.85,
            )
        )

    # Optional early search availability
    await upsert_ocr_into_index(
        db,
        org_id=run.org_id,
        asset_id=run.asset_id,
        ocr_data={"text": partial_text},
    )

    await db.commit()


async def _set_progress(
    db: AsyncSession,
    *,
    run_id: UUID,
    current: int,
    total: int | None,
    message: str | None,
) -> None:
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(
            progress_current=current,
            progress_total=total,
            progress_message=message,
        )
    )
    await db.commit()


def _ocr_images_from_pdf_iter(pdf_bytes: bytes, lang: str):
    try:
        from pdf2image import convert_from_bytes
    except Exception as e:
        raise RuntimeError(
            "Scanned-PDF OCR requires 'pdf2image' plus system Poppler. "
            f"Import/setup error: {str(e)}"
        )

    try:
        images = convert_from_bytes(pdf_bytes, first_page=1, last_page=MAX_PDF_OCR_PAGES)
    except Exception as e:
        raise RuntimeError(
            "Failed to rasterize PDF. This often means Poppler is missing or misconfigured. "
            f"Error: {str(e)}"
        )

    total = len(images)
    for i, img in enumerate(images, start=1):
        yield i, total, img


async def process_ocr_run(db: AsyncSession, run_id: UUID, lang: str = "eng") -> None:
    run = (await db.execute(select(IntelligenceRun).where(IntelligenceRun.id == run_id))).scalar_one()

    # If canceled before start, exit cleanly
    if await is_cancel_requested(db, org_id=run.org_id, run_id=run.id):
        await mark_run_canceled(db, org_id=run.org_id, run_id=run.id, message="canceled before start")
        return

    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(
            status="running",
            error_message=None,
            progress_current=0,
            progress_total=None,
            progress_message="starting",
        )
    )
    await db.commit()

    asset = (await db.execute(select(Asset).where(Asset.id == run.asset_id))).scalar_one()

    # Download content ONCE
    resp = requests.get(asset.source_uri, timeout=60)
    resp.raise_for_status()

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].lower()
    raw_bytes = resp.content

    # Check cancel after download
    if await is_cancel_requested(db, org_id=run.org_id, run_id=run.id):
        await mark_run_canceled(db, org_id=run.org_id, run_id=run.id, message="canceled after download")
        return

    extracted_text = ""
    truncated = False
    method = None

    if content_type.startswith("text/"):
        await _set_progress(db, run_id=run_id, current=1, total=1, message="downloaded text")

        try:
            extracted_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            extracted_text = raw_bytes.decode("latin-1", errors="replace")

        extracted_text, truncated = _truncate(extracted_text)
        method = "http_text"
        await _set_progress(db, run_id=run_id, current=1, total=1, message="text extracted")

    elif content_type == "application/pdf" or _looks_like_pdf(raw_bytes[:8]):
        await _set_progress(db, run_id=run_id, current=0, total=None, message="extracting embedded pdf text")

        pdf_text = _extract_pdf_text(raw_bytes)

        if len(pdf_text.strip()) >= PDF_MIN_TEXT_THRESHOLD:
            extracted_text = pdf_text
            extracted_text, truncated = _truncate(extracted_text)
            method = "pdf_text"
            await _set_progress(db, run_id=run_id, current=1, total=1, message="pdf embedded text extracted")
        else:
            # scanned PDF OCR (page loop supports cancellation)
            await _set_progress(db, run_id=run_id, current=0, total=None, message="pdf looks scanned; starting ocr")

            try:
                import pytesseract
            except Exception as e:
                raise RuntimeError(
                    "OCR requires pytesseract and system 'tesseract' binary installed. "
                    f"Import/setup error: {str(e)}"
                )

            texts: list[str] = []
            total_pages = None

            for page_i, total, img in _ocr_images_from_pdf_iter(raw_bytes, lang=lang):
                total_pages = total

                # Cancel between pages (fast stop)
                if await is_cancel_requested(db, org_id=run.org_id, run_id=run.id):
                    await mark_run_canceled(
                        db,
                        org_id=run.org_id,
                        run_id=run.id,
                        message=f"canceled during pdf ocr (page {page_i-1}/{total_pages})",
                    )
                    return

                await _set_progress(
                    db,
                    run_id=run_id,
                    current=page_i - 1,
                    total=total_pages,
                    message=f"ocr page {page_i}/{total_pages}",
                )

                page_text = pytesseract.image_to_string(img, lang=lang) or ""
                page_text = page_text.strip()
                if page_text:
                    texts.append(f"[page {page_i}]\n{page_text}")

                partial_joined = "\n\n".join(texts).strip()
                await _upsert_partial_result(
                    db,
                    run=run,
                    pages_completed=page_i,
                    pages_total=total_pages,
                    text_partial=partial_joined,
                )

            extracted_text = "\n\n".join(texts).strip()
            extracted_text, truncated = _truncate(extracted_text)
            method = "pdf_image_ocr"
            await _set_progress(
                db,
                run_id=run_id,
                current=total_pages or 0,
                total=total_pages,
                message="pdf ocr completed",
            )

    elif content_type.startswith("image/") or content_type == "application/octet-stream":
        await _set_progress(db, run_id=run_id, current=0, total=1, message="preparing image ocr")

        # Allow cancel before OCR begins
        if await is_cancel_requested(db, org_id=run.org_id, run_id=run.id):
            await mark_run_canceled(db, org_id=run.org_id, run_id=run.id, message="canceled before image ocr")
            return

        if not _looks_like_image(raw_bytes[:512]):
            if _looks_like_pdf(raw_bytes[:8]):
                pdf_text = _extract_pdf_text(raw_bytes)
                if len(pdf_text.strip()) >= PDF_MIN_TEXT_THRESHOLD:
                    extracted_text = pdf_text
                    extracted_text, truncated = _truncate(extracted_text)
                    method = "pdf_text"
                    await _set_progress(db, run_id=run_id, current=1, total=1, message="pdf embedded text extracted")
                else:
                    try:
                        import pytesseract
                    except Exception as e:
                        raise RuntimeError(
                            "OCR requires pytesseract and system 'tesseract' binary installed. "
                            f"Import/setup error: {str(e)}"
                        )

                    texts: list[str] = []
                    total_pages = None
                    for page_i, total, img in _ocr_images_from_pdf_iter(raw_bytes, lang=lang):
                        total_pages = total

                        if await is_cancel_requested(db, org_id=run.org_id, run_id=run.id):
                            await mark_run_canceled(
                                db,
                                org_id=run.org_id,
                                run_id=run.id,
                                message=f"canceled during pdf ocr (page {page_i-1}/{total_pages})",
                            )
                            return

                        await _set_progress(db, run_id=run_id, current=page_i - 1, total=total_pages, message=f"ocr page {page_i}/{total_pages}")

                        page_text = pytesseract.image_to_string(img, lang=lang) or ""
                        page_text = page_text.strip()
                        if page_text:
                            texts.append(f"[page {page_i}]\n{page_text}")

                        partial_joined = "\n\n".join(texts).strip()
                        await _upsert_partial_result(
                            db,
                            run=run,
                            pages_completed=page_i,
                            pages_total=total_pages,
                            text_partial=partial_joined,
                        )

                    extracted_text = "\n\n".join(texts).strip()
                    extracted_text, truncated = _truncate(extracted_text)
                    method = "pdf_image_ocr"
                    await _set_progress(db, run_id=run_id, current=total_pages or 0, total=total_pages, message="pdf ocr completed")
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
            await _set_progress(db, run_id=run_id, current=1, total=1, message="image ocr completed")

    else:
        raise RuntimeError(f"OCR processor does not support content-type '{content_type}'")

    # Final cancel check before writing final result
    if await is_cancel_requested(db, org_id=run.org_id, run_id=run.id):
        await mark_run_canceled(db, org_id=run.org_id, run_id=run.id, message="canceled before finalize")
        return

    data = {
        "text": extracted_text,
        "truncated": truncated,
        "content_type": content_type,
        "language": lang,
        "method": method,
        "text_length": len(extracted_text),
        "pdf_ocr_pages": MAX_PDF_OCR_PAGES if method == "pdf_image_ocr" else None,
    }

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

    await upsert_ocr_into_index(
        db,
        org_id=run.org_id,
        asset_id=run.asset_id,
        ocr_data={"text": extracted_text},
    )

    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(
            status="completed",
            completed_at=datetime.utcnow(),
            progress_message="completed",
        )
    )
    await db.commit()
