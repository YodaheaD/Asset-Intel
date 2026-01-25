from sqlalchemy.orm import Session
from uuid import UUID

from app.models.intelligence_run import IntelligenceRun
from app.models.intelligence_result import IntelligenceResult

def get_intelligence_for_asset(
    db: Session,
    asset_id: UUID,
    org_id: UUID
):
    """
    Returns all completed intelligence runs + results for an asset
    """
    runs = (
        db.query(IntelligenceRun)
        .filter(
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.status == "completed"
        )
        .order_by(IntelligenceRun.created_at.desc())
        .all()
    )

    response = []

    for run in runs:
        results = (
            db.query(IntelligenceResult)
            .filter(IntelligenceResult.run_id == run.id)
            .all()
        )

        response.append({
            "run_id": run.id,
            "processor": run.processor_name,
            "version": run.processor_version,
            "completed_at": run.completed_at,
            "results": [
                {
                    "type": r.type,
                    "data": r.data,
                    "confidence": r.confidence
                }
                for r in results
            ]
        })

    return response


def get_latest_intelligence_by_type(
    db: Session,
    asset_id: UUID,
    org_id: UUID,
    intel_type: str
):
    """
    Returns the most recent result of a given intelligence type
    """
    result = (
        db.query(IntelligenceResult)
        .join(IntelligenceRun)
        .filter(
            IntelligenceRun.asset_id == asset_id,
            IntelligenceRun.org_id == org_id,
            IntelligenceRun.status == "completed",
            IntelligenceResult.type == intel_type
        )
        .order_by(IntelligenceRun.completed_at.desc())
        .first()
    )

    if not result:
        return None

    return {
        "type": result.type,
        "data": result.data,
        "confidence": result.confidence,
        "run_id": result.run_id
    }
