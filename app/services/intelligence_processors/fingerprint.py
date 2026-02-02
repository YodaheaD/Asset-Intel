from __future__ import annotations

import hashlib
from uuid import UUID
from datetime import datetime
import requests

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset
from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult
from app.services.fingerprint_signature_service import _signature_from_fingerprint_data
from app.services.search_index_service import upsert_fingerprint_into_index


async def process_fingerprint_run(db: AsyncSession, run_id: UUID) -> None:
    # Load run
    run_res = await db.execute(
        select(IntelligenceRun).where(IntelligenceRun.id == run_id)
    )
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

    # Step 1: HEAD (cheap)
    head = requests.head(url, timeout=15, allow_redirects=True)
    head.raise_for_status()

    content_type = head.headers.get("Content-Type")
    content_length = head.headers.get("Content-Length")
    etag = head.headers.get("ETag")
    last_modified = head.headers.get("Last-Modified")

    sha256 = None

    # Step 2: Only download if we don't have an ETag (or you could also require sha256 always)
    if not etag:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()

        hasher = hashlib.sha256()
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                hasher.update(chunk)

        sha256 = hasher.hexdigest()

    data = {
        "content_type": content_type,
        "content_length": int(content_length) if content_length else None,
        "etag": etag,
        "last_modified": last_modified,
        "sha256": sha256,
    }

    # Compute + store signature on the run itself (Phase 6.2)
    sig = _signature_from_fingerprint_data(data)
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(input_fingerprint_signature=sig)
    )
    await db.commit()

    # Persist result
    db.add(
        IntelligenceResult(
            org_id=run.org_id,
            asset_id=run.asset_id,
            run_id=run.id,
            type="fingerprint",
            data=data,
            confidence=1.0,
        )
    )

    # Phase 6.5: Upsert fingerprint into search index for dedupe queries
    await upsert_fingerprint_into_index(
        db,
        org_id=run.org_id,
        asset_id=run.asset_id,
        fingerprint_data=data,
    )

    # Mark completed
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(status="completed", completed_at=datetime.utcnow())
    )
    await db.commit()
