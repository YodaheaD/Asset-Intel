from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.asset import Asset
from app.schemas.asset import AssetCreate


class AssetService:
    @staticmethod
    async def create_asset(
        db: AsyncSession,
        asset_in: AssetCreate,
    ) -> Asset:

        # Check for existing asset with same source_uri
        result = await db.execute(
            select(Asset).where(Asset.source_uri == asset_in.source_uri)
        )
        existing = result.scalar_one_or_none()

        if existing:
            return existing

        asset = Asset(
            source_uri=asset_in.source_uri,
            asset_type=asset_in.asset_type,
            asset_metadata=asset_in.asset_metadata,
        )

        db.add(asset)
        await db.commit()
        await db.refresh(asset)

        return asset