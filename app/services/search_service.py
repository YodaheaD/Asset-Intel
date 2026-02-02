from __future__ import annotations

from uuid import UUID
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_search_index import AssetSearchIndex


async def search_assets(
    db: AsyncSession,
    *,
    org_id: UUID,
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []

    ts_query = func.plainto_tsquery("english", q)
    rank = func.ts_rank_cd(AssetSearchIndex.ocr_tsv, ts_query)

    stmt = (
        select(AssetSearchIndex, rank.label("rank"))
        .where(
            AssetSearchIndex.org_id == org_id,
            AssetSearchIndex.ocr_tsv.is_not(None),
            AssetSearchIndex.ocr_tsv.op("@@")(ts_query),
        )
        .order_by(func.coalesce(rank, 0).desc(), AssetSearchIndex.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )

    rows = (await db.execute(stmt)).all()
    results: list[dict[str, Any]] = []
    for idx, r in rows:
        results.append(
            {
                "asset_id": str(idx.asset_id),
                "rank": float(r or 0),
                "ocr_preview": idx.ocr_text_preview,
                "sha256": idx.sha256,
                "etag": idx.etag,
                "content_type": idx.content_type,
                "updated_at": idx.updated_at,
            }
        )
    return results


async def find_duplicates(
    db: AsyncSession,
    *,
    org_id: UUID,
    sha256: str | None = None,
    etag: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not sha256 and not etag:
        return []

    stmt = select(AssetSearchIndex).where(AssetSearchIndex.org_id == org_id)

    if sha256:
        stmt = stmt.where(AssetSearchIndex.sha256 == sha256)
    if etag:
        stmt = stmt.where(AssetSearchIndex.etag == etag)

    stmt = stmt.order_by(AssetSearchIndex.updated_at.desc()).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "asset_id": str(r.asset_id),
            "sha256": r.sha256,
            "etag": r.etag,
            "content_type": r.content_type,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]
