def test_create_asset(client):
    payload = {
        "source_uri": "https://example.com/image.jpg",
        "asset_type": "image",
        "metadata": {
            "width": 1024,
            "height": 768
        }
    }

    response = client.post("/api/v1/assets", json=payload)

    assert response.status_code == 201
    body = response.json()

    assert body["source_uri"] == payload["source_uri"]
    assert body["asset_type"] == payload["asset_type"]
    assert "id" in body
    assert "created_at" in body


def test_asset_processing_lifecycle(client):
    payload = {
        "source_uri": "https://example.com/test.png",
        "asset_type": "image",
        "metadata": {}
    }

    create_resp = client.post("/api/v1/assets", json=payload)
    assert create_resp.status_code == 201

    asset_id = create_resp.json()["id"]

    get_resp = client.get(f"/api/v1/assets/{asset_id}")
    assert get_resp.status_code == 200

    assert get_resp.json()["status"] in [
        "pending",
        "processing",
        "completed"
    ]