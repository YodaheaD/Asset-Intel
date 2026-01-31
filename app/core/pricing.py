# cents, intentionally simple
PROCESSOR_PRICING = {
    "image-metadata": 1,  # $1.00 per run
    "asset-fingerprint": 1,  # $1.00 per run
    "ocr-text": 2,  # $2.00 per run
}

def estimate_cost(processor_name: str) -> int:
    return PROCESSOR_PRICING.get(processor_name, 0)
