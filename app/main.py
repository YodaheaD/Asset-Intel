from fastapi import FastAPI

# Import all models to populate Base.metadata
from app.models.organization import Organization
from app.models.api_key import ApiKey
from app.models.asset import Asset
from app.api.v1.router import router as api_router
from dotenv import load_dotenv
load_dotenv()
app = FastAPI(title="AssetIntel API")

app.include_router(api_router, prefix="/api/v1")
