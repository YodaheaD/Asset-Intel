"""
Common Pydantic models for the AssetIntel Backend API
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class HealthResponse(BaseModel):
    """
    Health check response model
    """
    status: str
    message: str
    timestamp: datetime
    version: str

class BaseResponse(BaseModel):
    """
    Base response model for consistent API responses
    """
    success: bool
    message: str
    data: Optional[dict] = None
    timestamp: datetime = datetime.utcnow()

class ErrorResponse(BaseModel):
    """
    Error response model
    """
    success: bool = False
    error: str
    message: str
    timestamp: datetime = datetime.utcnow()