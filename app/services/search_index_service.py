from __future__ import annotations

from datetime import datetime
from uuid import UUID
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import func

from app.models.asset_search_index import AssetSearchIndex


def _preview(text: str, max_chars: int = 1000) -> str:
    text = (text or "").strip()
    return text if len(text) <= max_chars else text[:max_chars] + "…"


async def upsert_fingerprint_into_index(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    fingerprint_data: dict[str, Any],
) -> None:
    insert_stmt = insert(AssetSearchIndex).values(
        org_id=org_id,
        asset_id=asset_id,
        sha256=fingerprint_data.get("sha256"),
        etag=fingerprint_data.get("etag"),
        content_type=fingerprint_data.get("content_type"),
        last_modified=fingerprint_data.get("last_modified"),
        updated_at=datetime.utcnow(),
    )
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=[AssetSearchIndex.org_id, AssetSearchIndex.asset_id],
        set_={
            "sha256": insert_stmt.excluded.sha256,
            "etag": insert_stmt.excluded.etag,
            "content_type": insert_stmt.excluded.content_type,
            "last_modified": insert_stmt.excluded.last_modified,
            "updated_at": insert_stmt.excluded.updated_at,
        },
    )

    await db.execute(stmt)
    await db.commit()


async def upsert_ocr_into_index(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
    ocr_data: dict[str, Any],
) -> None:
    text = (ocr_data.get("text") or "").strip()
    preview = _preview(text, 1000)

    # We store preview + a tsvector generated from the full text (truncated upstream)
    insert_stmt = insert(AssetSearchIndex).values(
        org_id=org_id,
        asset_id=asset_id,
        ocr_text_preview=preview,
        ocr_tsv=func.to_tsvector("english", text),
        updated_at=datetime.utcnow(),
    )
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=[AssetSearchIndex.org_id, AssetSearchIndex.asset_id],
        set_={
            "ocr_text_preview": insert_stmt.excluded.ocr_text_preview,
            "ocr_tsv": insert_stmt.excluded.ocr_tsv,
            "updated_at": insert_stmt.excluded.updated_at,
        },
    )

    await db.execute(stmt)
    await db.commit()
