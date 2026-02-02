from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_db
from app.api.deps import get_current_org_id
from app.services.search_service import search_assets, find_duplicates

router = APIRouter()


@router.get("/search/assets")
async def search_assets_endpoint(
    query: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    return {
        "query": query,
        "limit": limit,
        "offset": offset,
        "results": await search_assets(
            db,
            org_id=org_id,
            query=query,
            limit=limit,
            offset=offset,
        ),
    }


@router.get("/search/duplicates")
async def duplicates_endpoint(
    sha256: str | None = Query(None),
    etag: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    org_id: UUID = Depends(get_current_org_id),
):
    return {
        "sha256": sha256,
        "etag": etag,
        "results": await find_duplicates(
            db,
            org_id=org_id,
            sha256=sha256,
            etag=etag,
            limit=limit,
        ),
    }
