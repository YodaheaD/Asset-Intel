import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_asset_creation():
    async with AsyncClient(app=app, base_url="http://test") as client:
        headers = {"X-API-Key": "super-secret-api-key"}
        data = {
            "source_uri": "https://example.com/image.png",
            "asset_type": "image",
            "metadata": {"foo": "bar"}
        }
        response = await client.post("/v1/assets", headers=headers, json=data)
        assert response.status_code == 200
        json_data = response.json()
        assert "id" in json_data
