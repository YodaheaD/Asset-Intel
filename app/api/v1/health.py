"""
Health check endpoints for monitoring application status
"""
from fastapi import APIRouter
from datetime import datetime
from app.models.common import HealthResponse

router = APIRouter()
router = APIRouter(prefix="/health")  # <-- add prefix

@router.get("", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint to verify the API is running
    """
    return HealthResponse(
        status="healthy",
        message="AssetIntel Backend API is running",
        timestamp=datetime.utcnow(),
        version="1.0.0"
    )

@router.get("/ready", response_model=HealthResponse)
async def readiness_check():
    """
    Readiness check endpoint for Kubernetes deployments
    """
    # Add any readiness checks here (database connectivity, etc.)
    return HealthResponse(
        status="ready",
        message="AssetIntel Backend API is ready to accept requests",
        timestamp=datetime.utcnow(),
        version="1.0.0"
    )