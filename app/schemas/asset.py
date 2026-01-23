from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Dict, Any
from uuid import UUID
from app.models.asset import AssetStatus, AssetType
from urllib.parse import urlparse


class AssetCreate(BaseModel):
    """
    Schema for creating new assets in Cosmos DB.
    
    Following Cosmos DB best practices:
    - Embedded metadata within single item to minimize cross-partition queries
    - Keeps item size under 2MB limit with max_length constraints
    - Flexible metadata dict allows for varied asset properties without schema changes
    """
    
    # Source URI for the asset (file path, URL, etc.)
    # Limited to 2048 chars to prevent oversized items in Cosmos DB
    source_uri: str = Field(..., max_length=2048)
    
    # Asset type enum for categorization and query filtering
    # Good candidate for partition key component if using Hierarchical Partition Keys
    asset_type: AssetType
    
    # Flexible metadata storage as embedded document
    # Allows asset-specific properties without rigid schema
    # Default empty dict prevents null values in Cosmos DB
    asset_metadata: Dict[str, Any] = Field(default_factory=dict)

    # Field Validator to ensure source_uri is a valid absolute URI
    @field_validator("source_uri")
    @classmethod
    ## Function : validate_source_uri used to validate source_uri field
    def validate_source_uri(cls, v: str) -> str:
        parsed = urlparse(v)
        if not parsed.scheme or not parsed.netloc:
            # If its not a valid absolute URI, raise ValueError
            raise ValueError("source_uri must be a valid absolute URI")
        return v


class AssetRead(BaseModel):
    id: UUID
    source_uri: str
    asset_type: AssetType
    status: AssetStatus
    asset_metadata: Dict[str, Any]
    created_at: datetime
    processed_at: datetime | None

    class Config:
        from_attributes = True

class AssetInternal(AssetRead):
    """
    Internal schema for asset data.
    Currently identical to AssetRead but allows for future internal-only fields
    without breaking API contracts.
    """
    pass