from PIL import Image
import requests
from io import BytesIO


def extract_image_metadata(external_url: str) -> dict:
    response = requests.get(external_url, timeout=10)
    response.raise_for_status()

    img = Image.open(BytesIO(response.content))

    return {
        "width": img.width,
        "height": img.height,
        "format": img.format,
        "mode": img.mode
    }
