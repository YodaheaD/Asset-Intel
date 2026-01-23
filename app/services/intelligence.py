import asyncio
from datetime import datetime
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetStatus
from app.db.session import AsyncSessionLocal


async def process_asset(asset_id, db: AsyncSession):
    try:
        await db.execute(
            update(Asset)
            .where(Asset.id == asset_id)
            .values(status=AssetStatus.processing)
        )
        await db.commit()

        await asyncio.sleep(2)

        fake_metadata = {
            "processed": True,
            "confidence": 0.98,
            "labels": ["example", "stub"],
        }

        await db.execute(
            update(Asset)
            .where(Asset.id == asset_id)
            .values(
                status=AssetStatus.completed,
                processed_at=datetime.utcnow(),
                asset_metadata=fake_metadata,
            )
        )
        await db.commit()

    except Exception:
        await db.execute(
            update(Asset)
            .where(Asset.id == asset_id)
            .values(status=AssetStatus.failed)
        )
        await db.commit()
