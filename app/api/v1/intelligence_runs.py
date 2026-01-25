from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.session import get_async_db 
from app.models.intelligence_run import IntelligenceRun

router = APIRouter()


@router.get("/intelligence/runs/{run_id}")
def get_run_status(run_id: UUID, db: Session = Depends(get_async_db )):
    run = db.query(IntelligenceRun).get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "id": run.id,
        "status": run.status,
        "processor": run.processor_name,
        "version": run.processor_version,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "error": run.error_message
    }
