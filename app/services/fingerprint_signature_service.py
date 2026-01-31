from __future__ import annotations

from uuid import UUID
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult


def _signature_from_fingerprint_data(data: dict[str, Any]) -> str | None:
    """
    Prefer strongest identifiers:
    1) sha256 (content-based)
    2) etag (server-provided content identifier)
    3) content_length + last_modified (weaker but still useful)
    """
    sha256 = data.get("sha256")
    if sha256:
        return f"sha256:{sha256}"

    etag = data.get("etag")
    if etag:
        return f"etag:{etag}"

    clen = data.get("content_length")
    lm = data.get("last_modified")
    if clen is not None and lm:
        return f"lenlm:{clen}:{lm}"

    return None


async def get_latest_fingerprint_signature(
    db: AsyncSession,
    *,
    org_id: UUID,
    asset_id: UUID,
) -> str | None:
    """
    Returns the latest completed fingerprint signature for an asset, or None if unavailable.
    """
    stmt = (
        select(IntelligenceResult, IntelligenceRun)
        .join(IntelligenceRun, IntelligenceRun.id == IntelligenceResult.run_id)
        .where(
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.status == "completed",
            IntelligenceResult.type == "fingerprint",
        )
        .order_by(IntelligenceRun.completed_at.desc())
        .limit(1)
    )

    row = (await db.execute(stmt)).first()
    if not row:
        return None

    result, _run = row
    data = result.data or {}
    if not isinstance(data, dict):
        return None

    return _signature_from_fingerprint_data(data)
