from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime

from app.models.asset import Asset
from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult
from app.services.intelligence_processors.image_metadata import extract_image_metadata


async def enqueue_image_metadata(
    db: Session,
    asset_id: UUID,
    org_id: UUID,
    background_tasks
):
    run = IntelligenceRun(
        asset_id=asset_id,
        org_id=org_id,
        processor_name="image-metadata",
        processor_version="1.0.0",
        status="pending"
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    background_tasks.add_task(
        process_image_metadata,
        run.id
    )

    return run


async def process_image_metadata(run_id: UUID):
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        run = None
        try:
            # Get the intelligence run
            result = await db.execute(select(IntelligenceRun).where(IntelligenceRun.id == run_id))
            run = result.scalar_one_or_none()
            if not run:
                raise RuntimeError("Intelligence run not found")
            run.status = "running"
            await db.commit()

            # Get the asset
            result = await db.execute(select(Asset).where(Asset.id == run.asset_id))
            asset = result.scalar_one_or_none()
            if not asset:
                raise RuntimeError("Asset not found")

            metadata = extract_image_metadata(asset.source_uri)

            result = IntelligenceResult(
                run_id=run.id,
                type="image_metadata",
                data=metadata,
                confidence=1.0
            )

            db.add(result)
            run.status = "completed"
            run.completed_at = datetime.utcnow()

            await db.commit()

        except Exception as e:
            if run:
                run.status = "failed"
                run.error_message = str(e)
                await db.commit()
