from __future__ import annotations

from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.models.asset import Asset
from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult

from PIL import Image
import requests
from io import BytesIO


async def process_image_metadata_run(db: AsyncSession, run_id: UUID) -> None:
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

    # Fetch bytes from source_uri (Option B)
    resp = requests.get(asset.source_uri, timeout=15)
    resp.raise_for_status()

    img = Image.open(BytesIO(resp.content))
    data = {
        "width": img.width,
        "height": img.height,
        "format": img.format,
        "mode": img.mode,
    }

    # Store result
    result = IntelligenceResult(
        org_id=run.org_id,
        asset_id=run.asset_id,
        run_id=run.id,
        type="image_metadata",
        data=data,
        confidence=1.0,
    )
    db.add(result)

    # Mark completed
    await db.execute(
        update(IntelligenceRun)
        .where(IntelligenceRun.id == run_id)
        .values(status="completed", completed_at=datetime.utcnow())
    )
    await db.commit()

# def extract_image_metadata(external_url: str) -> dict:
#     response = requests.get(external_url, timeout=10)
#     response.raise_for_status()

#     img = Image.open(BytesIO(response.content))

#     return {
#         "width": img.width,
#         "height": img.height,
#         "format": img.format,
#         "mode": img.mode
#     }